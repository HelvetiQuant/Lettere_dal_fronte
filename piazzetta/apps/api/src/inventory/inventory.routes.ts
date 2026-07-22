import type { Express, Request, Response } from 'express';
import type { PrismaClient, Prisma } from '@prisma/client';
import { z } from 'zod';
import { currentUser, type RouteDeps } from '../http';
import { recordMovement, effectiveParLevel, InventoryError, type MovementType } from './inventory.service';

type Tx = Prisma.TransactionClient;

const MAG_ROLES = ['OWNER', 'MANAGER'];

export function registerInventoryRoutes(app: Express, prisma: PrismaClient, deps: RouteDeps): void {
  const { devAuth, requireRoles } = deps;

  // Giacenze correnti con stato low-stock.
  app.get('/api/v1/inventory/stock', devAuth, requireRoles(...MAG_ROLES), async (req: Request, res: Response) => {
    const user = currentUser(req);
    const products = await prisma.product.findMany({
      where: { venueId: user.venueId },
      include: { stock: true },
      orderBy: { name: 'asc' },
    });
    const rows = products.map((p) => {
      const qty = p.stock?.quantity ?? 0;
      const reorder = p.stock?.reorderLevel ?? 0;
      const par = effectiveParLevel(p.stock?.parLevel ?? 0, reorder);
      return {
        productId: p.id,
        name: p.name,
        category: p.category,
        unit: p.unit,
        quantity: qty,
        reorderLevel: reorder,
        parLevel: par,
        low: reorder > 0 && qty <= reorder,
      };
    });
    res.json({ items: rows, lowCount: rows.filter((r) => r.low).length });
  });

  // Solo prodotti sotto soglia (input per il riordino).
  app.get('/api/v1/inventory/low-stock', devAuth, requireRoles(...MAG_ROLES), async (req: Request, res: Response) => {
    const user = currentUser(req);
    const products = await prisma.product.findMany({
      where: { venueId: user.venueId, stock: { isNot: null } },
      include: { stock: true },
    });
    const low = products
      .filter((p) => (p.stock?.reorderLevel ?? 0) > 0 && (p.stock?.quantity ?? 0) <= (p.stock?.reorderLevel ?? 0))
      .map((p) => ({ productId: p.id, name: p.name, quantity: p.stock!.quantity, reorderLevel: p.stock!.reorderLevel }));
    res.json(low);
  });

  // Rettifica manuale di magazzino (carico, scarto, reso, inventario fisico).
  const adjustSchema = z.object({
    productId: z.string(),
    type: z.enum(['LOAD', 'WASTE', 'RETURN', 'PHYSICAL']),
    qty: z.number().int(), // per PHYSICAL può essere negativo (delta); per gli altri positivo
    reason: z.string().optional(),
  });

  app.post('/api/v1/inventory/movements', devAuth, requireRoles(...MAG_ROLES), async (req: Request, res: Response) => {
    const user = currentUser(req);
    const body = adjustSchema.parse(req.body);
    if (body.type !== 'PHYSICAL' && body.qty <= 0) {
      res.status(400).json({ error: 'Quantità deve essere positiva' });
      return;
    }
    try {
      const qtyAfter = await prisma.$transaction((tx: Tx) =>
        recordMovement(tx, user.venueId, {
          productId: body.productId,
          type: body.type as MovementType,
          qty: body.qty,
          reason: body.reason,
          createdBy: user.userId,
        }),
      );
      res.status(201).json({ productId: body.productId, quantity: qtyAfter });
    } catch (e) {
      if (e instanceof InventoryError) {
        res.status(e.status).json({ error: e.message });
        return;
      }
      throw e;
    }
  });

  // Storico movimenti (per prodotto o generale), base per report sprechi/consumi.
  app.get('/api/v1/inventory/movements', devAuth, requireRoles(...MAG_ROLES), async (req: Request, res: Response) => {
    const user = currentUser(req);
    const productId = req.query.productId as string | undefined;
    const type = req.query.type as string | undefined;
    const movements = await prisma.stockMovement.findMany({
      where: {
        product: { venueId: user.venueId },
        ...(productId ? { productId } : {}),
        ...(type ? { type } : {}),
      },
      include: { product: { select: { name: true, unit: true } } },
      orderBy: { createdAt: 'desc' },
      take: 200,
    });
    res.json(movements);
  });

  // Imposta soglie: reorderLevel (trigger) e parLevel (target).
  const levelsSchema = z.object({
    reorderLevel: z.number().int().nonnegative().optional(),
    parLevel: z.number().int().nonnegative().optional(),
  });
  app.patch('/api/v1/inventory/stock/:productId/levels', devAuth, requireRoles(...MAG_ROLES), async (req: Request, res: Response) => {
    const user = currentUser(req);
    const productId = req.params.productId as string;
    const body = levelsSchema.parse(req.body);
    const product = await prisma.product.findFirst({ where: { id: productId, venueId: user.venueId }, include: { stock: true } });
    if (!product) {
      res.status(404).json({ error: 'Prodotto non trovato' });
      return;
    }
    const stock = await prisma.stockItem.upsert({
      where: { productId },
      update: body,
      create: { productId, quantity: 0, ...body },
    });
    res.json(stock);
  });
}

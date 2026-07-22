import type { Express, Request, Response } from 'express';
import type { PrismaClient, Prisma } from '@prisma/client';
import { z } from 'zod';
import { currentUser, type RouteDeps } from '../http';
import { recordMovement } from '../inventory/inventory.service';
import { canPoTransition, applyReceipt, type PoStatus, type PoItemState } from './purchase.logic';

type Tx = Prisma.TransactionClient;
const SUP_ROLES = ['OWNER', 'MANAGER'];

export function registerPurchaseRoutes(app: Express, prisma: PrismaClient, deps: RouteDeps): void {
  const { devAuth, requireRoles } = deps;

  // ---- Crea ordine d'acquisto (manuale o da proposta) ----
  const createSchema = z.object({
    supplierId: z.string(),
    note: z.string().optional(),
    items: z
      .array(
        z.object({
          productId: z.string(),
          packSize: z.number().int().positive().default(1),
          packsOrdered: z.number().int().positive(),
          packPriceCents: z.number().int().nonnegative().default(0),
        }),
      )
      .min(1),
  });

  app.post('/api/v1/purchase-orders', devAuth, requireRoles(...SUP_ROLES), async (req: Request, res: Response) => {
    const user = currentUser(req);
    const body = createSchema.parse(req.body);

    const supplier = await prisma.supplier.findFirst({ where: { id: body.supplierId, venueId: user.venueId } });
    if (!supplier) {
      res.status(400).json({ error: 'Fornitore non valido' });
      return;
    }
    const productIds = body.items.map((i) => i.productId);
    const products = await prisma.product.findMany({ where: { id: { in: productIds }, venueId: user.venueId }, select: { id: true } });
    if (products.length !== new Set(productIds).size) {
      res.status(400).json({ error: 'Prodotto non valido' });
      return;
    }

    const total = body.items.reduce((s, i) => s + i.packsOrdered * i.packPriceCents, 0);
    const po = await prisma.purchaseOrder.create({
      data: {
        venueId: user.venueId,
        supplierId: body.supplierId,
        status: 'DRAFT',
        note: body.note,
        createdBy: user.userId,
        totalCents: total,
        items: {
          create: body.items.map((i) => ({
            productId: i.productId,
            packSize: i.packSize,
            packsOrdered: i.packsOrdered,
            packPriceCents: i.packPriceCents,
          })),
        },
      },
      include: { items: true, supplier: true },
    });
    res.status(201).json(po);
  });

  // ---- Lista ordini d'acquisto ----
  app.get('/api/v1/purchase-orders', devAuth, requireRoles(...SUP_ROLES), async (req: Request, res: Response) => {
    const user = currentUser(req);
    const status = req.query.status as string | undefined;
    const pos = await prisma.purchaseOrder.findMany({
      where: { venueId: user.venueId, ...(status ? { status } : {}) },
      include: { supplier: { select: { name: true } }, items: { include: { product: { select: { name: true, unit: true } } } } },
      orderBy: { createdAt: 'desc' },
    });
    res.json(pos);
  });

  // ---- Invia al fornitore (DRAFT -> SENT) ----
  app.post('/api/v1/purchase-orders/:id/send', devAuth, requireRoles(...SUP_ROLES), async (req: Request, res: Response) => {
    const user = currentUser(req);
    const id = req.params.id as string;
    const po = await prisma.purchaseOrder.findFirst({ where: { id, venueId: user.venueId } });
    if (!po) {
      res.status(404).json({ error: 'Ordine non trovato' });
      return;
    }
    if (!canPoTransition(po.status as PoStatus, 'SENT')) {
      res.status(409).json({ error: `Transizione non consentita: ${po.status} -> SENT` });
      return;
    }
    const updated = await prisma.purchaseOrder.update({ where: { id }, data: { status: 'SENT', sentAt: new Date() } });
    res.json(updated);
  });

  // ---- Annulla (DRAFT/SENT -> CANCELLED) ----
  app.post('/api/v1/purchase-orders/:id/cancel', devAuth, requireRoles(...SUP_ROLES), async (req: Request, res: Response) => {
    const user = currentUser(req);
    const id = req.params.id as string;
    const po = await prisma.purchaseOrder.findFirst({ where: { id, venueId: user.venueId } });
    if (!po) {
      res.status(404).json({ error: 'Ordine non trovato' });
      return;
    }
    if (!canPoTransition(po.status as PoStatus, 'CANCELLED')) {
      res.status(409).json({ error: `Non annullabile in stato ${po.status}` });
      return;
    }
    const updated = await prisma.purchaseOrder.update({ where: { id }, data: { status: 'CANCELLED' } });
    res.json(updated);
  });

  // ---- Ricezione merce (totale o parziale) ----
  const receiveSchema = z.object({
    lines: z.array(z.object({ itemId: z.string(), packs: z.number().int().nonnegative() })).min(1),
  });

  app.post('/api/v1/purchase-orders/:id/receive', devAuth, requireRoles(...SUP_ROLES), async (req: Request, res: Response) => {
    const user = currentUser(req);
    const id = req.params.id as string;
    const body = receiveSchema.parse(req.body);

    const po = await prisma.purchaseOrder.findFirst({ where: { id, venueId: user.venueId }, include: { items: true } });
    if (!po) {
      res.status(404).json({ error: 'Ordine non trovato' });
      return;
    }
    if (po.status !== 'SENT' && po.status !== 'PARTIAL') {
      res.status(409).json({ error: `Ricezione non consentita in stato ${po.status}` });
      return;
    }

    const itemsState: Record<string, PoItemState> = {};
    for (const it of po.items) itemsState[it.id] = { packsOrdered: it.packsOrdered, packsReceived: it.packsReceived };
    const outcome = applyReceipt(itemsState, body.lines);

    const updated = await prisma.$transaction(async (tx: Tx) => {
      for (const line of outcome.lines) {
        if (line.acceptedPacks <= 0) continue;
        const item = po.items.find((i) => i.id === line.itemId)!;
        // aggiorna righe ricevute
        await tx.purchaseOrderItem.update({ where: { id: item.id }, data: { packsReceived: line.newPacksReceived } });
        // incrementa la giacenza in unità BASE e storicizza (RECEIPT)
        await recordMovement(tx, user.venueId, {
          productId: item.productId,
          type: 'RECEIPT',
          qty: line.acceptedPacks * item.packSize,
          reason: `Ricezione ordine ${id.slice(-6)}`,
          createdBy: user.userId,
        });
      }
      return tx.purchaseOrder.update({
        where: { id },
        data: {
          status: outcome.status,
          receivedAt: outcome.status === 'RECEIVED' ? new Date() : null,
        },
        include: { items: { include: { product: { select: { name: true, unit: true } } } }, supplier: { select: { name: true } } },
      });
    });

    res.json(updated);
  });
}

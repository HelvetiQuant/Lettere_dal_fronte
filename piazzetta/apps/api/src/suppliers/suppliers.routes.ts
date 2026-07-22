import type { Express, Request, Response } from 'express';
import type { PrismaClient } from '@prisma/client';
import { z } from 'zod';
import { currentUser, type RouteDeps } from '../http';
import { computeReorder } from './reorder.logic';

const SUP_ROLES = ['OWNER', 'MANAGER'];

export function registerSupplierRoutes(app: Express, prisma: PrismaClient, deps: RouteDeps): void {
  const { devAuth, requireRoles } = deps;

  // ---- Anagrafica fornitori ----
  const supplierSchema = z.object({
    name: z.string().min(1),
    email: z.string().email().optional(),
    phone: z.string().optional(),
    notes: z.string().optional(),
  });

  app.get('/api/v1/suppliers', devAuth, requireRoles(...SUP_ROLES), async (req: Request, res: Response) => {
    const user = currentUser(req);
    const suppliers = await prisma.supplier.findMany({
      where: { venueId: user.venueId, active: true },
      include: { _count: { select: { listings: true } } },
      orderBy: { name: 'asc' },
    });
    res.json(suppliers);
  });

  app.post('/api/v1/suppliers', devAuth, requireRoles(...SUP_ROLES), async (req: Request, res: Response) => {
    const user = currentUser(req);
    const body = supplierSchema.parse(req.body);
    const supplier = await prisma.supplier.create({ data: { venueId: user.venueId, ...body } });
    res.status(201).json(supplier);
  });

  app.patch('/api/v1/suppliers/:id', devAuth, requireRoles(...SUP_ROLES), async (req: Request, res: Response) => {
    const user = currentUser(req);
    const id = req.params.id as string;
    const body = supplierSchema.partial().extend({ active: z.boolean().optional() }).parse(req.body);
    const existing = await prisma.supplier.findFirst({ where: { id, venueId: user.venueId } });
    if (!existing) {
      res.status(404).json({ error: 'Fornitore non trovato' });
      return;
    }
    const supplier = await prisma.supplier.update({ where: { id }, data: body });
    res.json(supplier);
  });

  // ---- Listino del fornitore ----
  app.get('/api/v1/suppliers/:id/listings', devAuth, requireRoles(...SUP_ROLES), async (req: Request, res: Response) => {
    const user = currentUser(req);
    const id = req.params.id as string;
    const supplier = await prisma.supplier.findFirst({ where: { id, venueId: user.venueId } });
    if (!supplier) {
      res.status(404).json({ error: 'Fornitore non trovato' });
      return;
    }
    const listings = await prisma.supplierProduct.findMany({
      where: { supplierId: id },
      include: { product: { select: { name: true, unit: true } } },
      orderBy: { createdAt: 'asc' },
    });
    res.json(listings);
  });

  const listingSchema = z.object({
    productId: z.string(),
    supplierSku: z.string().optional(),
    packSize: z.number().int().positive().default(1),
    packPriceCents: z.number().int().nonnegative().default(0),
    leadTimeDays: z.number().int().nonnegative().default(2),
    preferred: z.boolean().default(false),
  });

  app.post('/api/v1/suppliers/:id/listings', devAuth, requireRoles(...SUP_ROLES), async (req: Request, res: Response) => {
    const user = currentUser(req);
    const id = req.params.id as string;
    const body = listingSchema.parse(req.body);
    const supplier = await prisma.supplier.findFirst({ where: { id, venueId: user.venueId } });
    if (!supplier) {
      res.status(404).json({ error: 'Fornitore non trovato' });
      return;
    }
    const product = await prisma.product.findFirst({ where: { id: body.productId, venueId: user.venueId } });
    if (!product) {
      res.status(400).json({ error: 'Prodotto non valido' });
      return;
    }
    const listing = await prisma.supplierProduct.upsert({
      where: { supplierId_productId: { supplierId: id, productId: body.productId } },
      update: body,
      create: { supplierId: id, ...body },
    });
    res.status(201).json(listing);
  });

  // ---- Proposte di riordino (par level), raggruppate per fornitore ----
  app.get('/api/v1/suppliers/reorder-proposals', devAuth, requireRoles(...SUP_ROLES), async (req: Request, res: Response) => {
    const user = currentUser(req);

    // Prodotti con giacenza sotto soglia.
    const products = await prisma.product.findMany({
      where: { venueId: user.venueId, stock: { isNot: null } },
      include: { stock: true, listings: { include: { supplier: true } } },
    });

    type Line = {
      productId: string;
      name: string;
      unit: string;
      quantity: number;
      reorderLevel: number;
      targetLevel: number;
      packSize: number;
      packs: number;
      orderedBase: number;
      packPriceCents: number;
      lineCostCents: number;
    };
    const bySupplier = new Map<string, { supplierId: string; supplierName: string; lines: Line[]; totalCents: number }>();
    const unassigned: { productId: string; name: string; deficitBase: number }[] = [];

    for (const p of products) {
      const stock = p.stock!;
      // Scegli il listino: preferito, altrimenti il più economico per unità base.
      const listings = p.listings.filter((l) => l.supplier.active);
      const chosen =
        listings.find((l) => l.preferred) ??
        listings.slice().sort((a, b) => a.packPriceCents / Math.max(1, a.packSize) - b.packPriceCents / Math.max(1, b.packSize))[0];

      const sug = computeReorder({
        quantity: stock.quantity,
        reorderLevel: stock.reorderLevel,
        parLevel: stock.parLevel,
        packSize: chosen?.packSize ?? 1,
      });
      if (!sug.needed) continue;

      if (!chosen) {
        unassigned.push({ productId: p.id, name: p.name, deficitBase: sug.deficitBase });
        continue;
      }

      const lineCost = sug.packs * chosen.packPriceCents;
      const g = bySupplier.get(chosen.supplierId) ?? {
        supplierId: chosen.supplierId,
        supplierName: chosen.supplier.name,
        lines: [],
        totalCents: 0,
      };
      g.lines.push({
        productId: p.id,
        name: p.name,
        unit: p.unit,
        quantity: stock.quantity,
        reorderLevel: stock.reorderLevel,
        targetLevel: sug.targetLevel,
        packSize: sug.packSize,
        packs: sug.packs,
        orderedBase: sug.orderedBase,
        packPriceCents: chosen.packPriceCents,
        lineCostCents: lineCost,
      });
      g.totalCents += lineCost;
      bySupplier.set(chosen.supplierId, g);
    }

    res.json({
      proposals: Array.from(bySupplier.values()).sort((a, b) => b.totalCents - a.totalCents),
      unassigned, // prodotti sotto soglia senza fornitore a listino
    });
  });
}

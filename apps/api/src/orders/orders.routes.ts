import type { Express, Request, Response } from 'express';
import type { PrismaClient, Prisma } from '@prisma/client';
import { z } from 'zod';
import { currentUser, type RouteDeps } from '../http';
import { stationForCategory, ALL_STATIONS, type Station } from '../stations/stations';
import { recordMovement } from '../inventory/inventory.service';

type Tx = Prisma.TransactionClient;

/**
 * Macchina a stati dell'ordine e transizioni consentite. Ogni transizione può
 * scrivere timestamp usati poi dalle statistiche tempi.
 *
 *   DRAFT ─▶ SENT ─▶ IN_PREPARATION ─▶ READY ─▶ SERVED ─▶ PAID
 *                                                   └─▶ CANCELLED (da quasi ovunque)
 */
const ORDER_TRANSITIONS: Record<string, string[]> = {
  DRAFT: ['SENT', 'CANCELLED'],
  SENT: ['IN_PREPARATION', 'CANCELLED'],
  IN_PREPARATION: ['READY', 'CANCELLED'],
  READY: ['SERVED', 'CANCELLED'],
  SERVED: ['PAID', 'CANCELLED'],
  PAID: [],
  CANCELLED: [],
};

export function canTransition(from: string, to: string): boolean {
  return (ORDER_TRANSITIONS[from] ?? []).includes(to);
}

/** Applica a un OrderItem i timestamp coerenti con il nuovo stato dell'ordine. */
export function itemTimestampsFor(status: string, now: Date): Partial<Record<'sentAt' | 'startedAt' | 'readyAt' | 'servedAt', Date>> {
  switch (status) {
    case 'SENT':
      return { sentAt: now };
    case 'IN_PREPARATION':
      return { startedAt: now };
    case 'READY':
      return { readyAt: now };
    case 'SERVED':
      return { servedAt: now };
    default:
      return {};
  }
}

/** Applica all'Order i timestamp coerenti con il nuovo stato. */
export function orderTimestampsFor(status: string, now: Date): Partial<Record<'sentAt' | 'servedAt' | 'paidAt', Date>> {
  switch (status) {
    case 'SENT':
      return { sentAt: now };
    case 'SERVED':
      return { servedAt: now };
    case 'PAID':
      return { paidAt: now };
    default:
      return {};
  }
}

export function registerOrderRoutes(app: Express, prisma: PrismaClient, deps: RouteDeps): void {
  const { devAuth, requireRoles } = deps;

  const createOrderSchema = z.object({
    sessionId: z.string(),
    clientOrderId: z.string().optional(),
    items: z.array(z.object({ productId: z.string(), quantity: z.number().int().positive() })).min(1),
  });

  /**
   * Crea una comanda. La station di ogni riga viene derivata dalla category del
   * prodotto e DENORMALIZZATA su OrderItem.station. L'ordine parte già in SENT
   * (comanda inviata a bar/cucina) con `placedAt` = ora della presa comanda.
   */
  app.post('/api/v1/orders-tables/orders', devAuth, requireRoles('OWNER', 'MANAGER', 'WAITER'), async (req: Request, res: Response) => {
    const user = currentUser(req);
    const body = createOrderSchema.parse(req.body);
    const now = new Date();

    const productIds = body.items.map((i) => i.productId);
    const products = await prisma.product.findMany({
      where: { id: { in: productIds }, venueId: user.venueId },
      include: { stock: true, recipeItems: true },
    });
    if (products.length !== new Set(productIds).size) {
      res.status(400).json({ error: 'Invalid product' });
      return;
    }

    const session = await prisma.tableSession.findFirst({
      where: { id: body.sessionId, state: 'OPEN', table: { venueId: user.venueId } },
    });
    if (!session) {
      res.status(400).json({ error: 'Invalid or closed session' });
      return;
    }

    const order = await prisma.$transaction(async (tx: Tx) => {
      if (body.clientOrderId) {
        const existing = await tx.order.findUnique({
          where: { clientOrderId: body.clientOrderId },
          include: { items: { include: { product: true } } },
        });
        if (existing) return existing; // idempotenza offline
      }

      let total = 0;
      const created = await tx.order.create({
        data: {
          sessionId: body.sessionId,
          clientOrderId: body.clientOrderId,
          status: 'SENT',
          placedAt: now,
          sentAt: now,
          items: {
            create: body.items.map((i) => {
              const product = products.find((p) => p.id === i.productId)!;
              total += product.priceCents * i.quantity;
              return {
                productId: i.productId,
                quantity: i.quantity,
                unitCents: product.priceCents,
                status: 'PENDING',
                station: stationForCategory(product.category),
                sentAt: now,
              };
            }),
          },
        },
        include: { items: { include: { product: true } } },
      });

      // Scarico automatico con storicizzazione (SALE). Se il prodotto ha una
      // distinta base, scala gli ingredienti; altrimenti scala sé stesso.
      for (const i of body.items) {
        const product = products.find((p) => p.id === i.productId)!;
        if (product.recipeItems.length > 0) {
          for (const ri of product.recipeItems) {
            await recordMovement(tx, user.venueId, {
              productId: ri.ingredientId,
              type: 'SALE',
              qty: ri.amount * i.quantity,
              orderId: created.id,
              createdBy: user.userId,
            });
          }
        } else if (product.stock) {
          await recordMovement(tx, user.venueId, {
            productId: product.id,
            type: 'SALE',
            qty: i.quantity,
            orderId: created.id,
            createdBy: user.userId,
          });
        }
      }

      return tx.order.update({
        where: { id: created.id },
        data: { totalCents: total },
        include: { items: { include: { product: true } } },
      });
    });

    res.status(201).json(order);
  });

  const statusSchema = z.object({
    status: z.enum(['DRAFT', 'SENT', 'IN_PREPARATION', 'READY', 'SERVED', 'CANCELLED', 'PAID']),
  });

  /**
   * Avanza lo stato di un ORDINE (tutte le sue righe insieme). Valida la
   * transizione e scrive i timestamp su ordine e righe.
   */
  app.patch('/api/v1/orders-tables/orders/:id/status', devAuth, async (req: Request, res: Response) => {
    const user = currentUser(req);
    const id = req.params.id as string;
    const { status } = statusSchema.parse(req.body);
    const now = new Date();

    const order = await prisma.order.findFirst({
      where: { id, session: { table: { venueId: user.venueId } } },
    });
    if (!order) {
      res.status(404).json({ error: 'Order not found' });
      return;
    }
    if (!canTransition(order.status, status)) {
      res.status(409).json({ error: `Transizione non consentita: ${order.status} -> ${status}` });
      return;
    }

    const updated = await prisma.$transaction(async (tx: Tx) => {
      const o = await tx.order.update({
        where: { id },
        data: { status, ...orderTimestampsFor(status, now) },
      });
      const itemTs = itemTimestampsFor(status, now);
      if (Object.keys(itemTs).length > 0) {
        // avanza le righe non ancora oltre questo step (non riscrive timestamp già impostati)
        await tx.orderItem.updateMany({
          where: { orderId: id },
          data: { status, ...itemTs },
        });
      }
      return o;
    });

    res.json(updated);
  });

  const itemStatusSchema = z.object({
    status: z.enum(['PENDING', 'IN_PREPARATION', 'READY', 'SERVED', 'CANCELLED']),
  });

  /**
   * Avanza lo stato di una SINGOLA riga (utile quando bar e cucina lavorano a
   * ritmi diversi: la stessa comanda ha righe pronte in tempi differenti).
   */
  app.patch('/api/v1/orders-tables/order-items/:id/status', devAuth, async (req: Request, res: Response) => {
    const user = currentUser(req);
    const id = req.params.id as string;
    const { status } = itemStatusSchema.parse(req.body);
    const now = new Date();

    const item = await prisma.orderItem.findFirst({
      where: { id, order: { session: { table: { venueId: user.venueId } } } },
    });
    if (!item) {
      res.status(404).json({ error: 'Order item not found' });
      return;
    }

    const ts = itemTimestampsFor(status, now);
    const updated = await prisma.orderItem.update({ where: { id }, data: { status, ...ts } });
    res.json(updated);
  });

  /**
   * Board ordini per postazione. `?station=BAR|TAVOLA_CALDA` filtra le righe;
   * default raggruppa entrambe. Restituisce le comande con le sole righe della
   * postazione richiesta e i tempi trascorsi, pronte per il KDS del bar / cucina.
   */
  app.get('/api/v1/orders-tables/board', devAuth, async (req: Request, res: Response) => {
    const user = currentUser(req);
    const stationParam = (req.query.station as string | undefined)?.toUpperCase();
    const station = ALL_STATIONS.includes(stationParam as Station) ? (stationParam as Station) : undefined;

    const orders = await prisma.order.findMany({
      where: {
        session: { table: { venueId: user.venueId } },
        status: { in: ['SENT', 'IN_PREPARATION', 'READY'] },
        ...(station ? { items: { some: { station } } } : {}),
      },
      include: {
        items: { where: station ? { station } : undefined, include: { product: true } },
        session: { include: { table: true } },
      },
      orderBy: { placedAt: 'asc' },
    });

    const now = Date.now();
    const board = orders.map((o) => ({
      id: o.id,
      table: o.session.table.name,
      status: o.status,
      placedAt: o.placedAt,
      waitingSec: Math.round((now - new Date(o.placedAt).getTime()) / 1000),
      items: o.items.map((it) => ({
        id: it.id,
        name: it.product.name,
        quantity: it.quantity,
        station: it.station,
        status: it.status,
      })),
    }));

    if (station) {
      res.json({ station, orders: board });
      return;
    }
    // Senza filtro: due colonne pronte per la dashboard.
    res.json({
      BAR: board.map((b) => ({ ...b, items: b.items.filter((i) => i.station === 'BAR') })).filter((b) => b.items.length),
      TAVOLA_CALDA: board.map((b) => ({ ...b, items: b.items.filter((i) => i.station === 'TAVOLA_CALDA') })).filter((b) => b.items.length),
    });
  });
}

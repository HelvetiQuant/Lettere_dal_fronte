import type { Express, Request, Response } from 'express';
import type { PrismaClient } from '@prisma/client';
import { z } from 'zod';
import { currentUser, type RouteDeps } from '../http';
import { ALL_STATIONS, type Station } from '../stations/stations';
import { aggregateItems, aggregateDelivery, type ItemTiming, type OrderTiming, type GroupBy } from './prep-time';

const querySchema = z.object({
  from: z.string().datetime().optional(),
  to: z.string().datetime().optional(),
  station: z.enum(['BAR', 'TAVOLA_CALDA']).optional(),
  groupBy: z.enum(['station', 'category', 'product']).default('category'),
});

export function registerStatsRoutes(app: Express, prisma: PrismaClient, deps: RouteDeps): void {
  const { devAuth, requireRoles } = deps;

  /**
   * Statistiche tempi di preparazione. Solo titolare/manager.
   * GET /api/v1/stats/prep-times?from=&to=&station=&groupBy=category|product|station
   *
   * Ritorna:
   *  - groups[]: per ciascun gruppo (piatto/cocktail o categoria o postazione)
   *      queue / prep / stationTotal con count, media, mediana, p90, min, max (sec)
   *  - delivery: tempo ordine->consegna al tavolo aggregato
   *  - byStation: sintesi rapida BAR vs TAVOLA_CALDA
   */
  app.get('/api/v1/stats/prep-times', devAuth, requireRoles('OWNER', 'MANAGER'), async (req: Request, res: Response) => {
    const user = currentUser(req);
    const q = querySchema.parse(req.query);
    const groupBy = q.groupBy as GroupBy;

    // Default: ultime 24h se non specificato.
    const to = q.to ? new Date(q.to) : new Date();
    const from = q.from ? new Date(q.from) : new Date(to.getTime() - 24 * 3600 * 1000);

    const orders = await prisma.order.findMany({
      where: {
        session: { table: { venueId: user.venueId } },
        placedAt: { gte: from, lte: to },
        status: { in: ['READY', 'SERVED', 'PAID'] },
      },
      select: {
        placedAt: true,
        servedAt: true,
        items: {
          where: q.station ? { station: q.station } : undefined,
          select: {
            productId: true,
            station: true,
            sentAt: true,
            startedAt: true,
            readyAt: true,
            servedAt: true,
            product: { select: { name: true, category: true } },
          },
        },
      },
    });

    const items: ItemTiming[] = orders.flatMap((o) =>
      o.items.map((it) => ({
        productId: it.productId,
        productName: it.product.name,
        category: it.product.category,
        station: it.station,
        sentAt: it.sentAt,
        startedAt: it.startedAt,
        readyAt: it.readyAt,
        servedAt: it.servedAt,
      })),
    );
    const orderTimings: OrderTiming[] = orders.map((o) => ({ placedAt: o.placedAt, servedAt: o.servedAt }));

    const groups = aggregateItems(items, groupBy);
    const delivery = aggregateDelivery(orderTimings);

    const byStation = ALL_STATIONS.map((s: Station) => {
      const stationItems = items.filter((i) => i.station === s);
      const agg = aggregateItems(stationItems, 'station');
      return { station: s, ...(agg[0] ?? { stationTotal: { count: 0 } }) };
    });

    res.json({
      range: { from, to },
      groupBy,
      station: q.station ?? 'ALL',
      groups,
      delivery,
      byStation,
    });
  });
}

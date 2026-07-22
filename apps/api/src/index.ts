import 'dotenv/config';
import cors from 'cors';
import express, { Request, Response, NextFunction, RequestHandler } from 'express';
import { PrismaClient, Prisma } from '@prisma/client';
import { z } from 'zod';
import type { DevUser, RouteDeps } from './http';
import { registerOrderRoutes } from './orders/orders.routes';
import { registerStatsRoutes } from './stats/stats.routes';
import { registerCreditRoutes } from './credit/credit.routes';
import { registerInventoryRoutes } from './inventory/inventory.routes';
import { registerSupplierRoutes } from './suppliers/suppliers.routes';
import { registerPurchaseRoutes } from './suppliers/purchase.routes';

const prisma = new PrismaClient();
const app = express();

type Tx = Prisma.TransactionClient;

app.use(cors());
app.use(express.json());

const devAuth: RequestHandler = (req: Request, res: Response, next: NextFunction) => {
  const venueId = req.headers['x-venue-id'] as string;
  const userId = req.headers['x-user-id'] as string;
  const rolesHeader = req.headers['x-user-roles'] as string;
  if (!venueId || !userId || !rolesHeader) {
    res.status(401).json({ error: 'Missing dev auth headers' });
    return;
  }
  (req as any).devUser = { venueId, userId, roles: rolesHeader.split(',') } as DevUser;
  next();
};

function requireRoles(...allowed: string[]): RequestHandler {
  return (req: Request, res: Response, next: NextFunction) => {
    const user = (req as any).devUser as DevUser;
    if (!user || !user.roles.some((r) => allowed.includes(r) || r === 'OWNER')) {
      res.status(403).json({ error: 'Forbidden' });
      return;
    }
    next();
  };
}

const deps: RouteDeps = { devAuth, requireRoles };

app.get('/api/v1/health', (_req: Request, res: Response) => {
  res.json({ ok: true, service: 'la-piazzetta-api' });
});

// --- Tavoli e sessioni (invariati) ---
app.get('/api/v1/orders-tables/tables', devAuth, async (req: Request, res: Response) => {
  const user = (req as any).devUser as DevUser;
  const tables = await prisma.table.findMany({
    where: { venueId: user.venueId },
    orderBy: { code: 'asc' },
    include: { sessions: { where: { state: 'OPEN' }, take: 1 } },
  });
  res.json(tables);
});

const createTableSchema = z.object({
  code: z.string().min(1),
  name: z.string().min(1),
  area: z.enum(['indoor', 'outdoor']).default('indoor'),
  seats: z.number().int().positive().default(4),
});

app.post('/api/v1/orders-tables/tables', devAuth, requireRoles('OWNER', 'MANAGER'), async (req: Request, res: Response) => {
  const user = (req as any).devUser as DevUser;
  const body = createTableSchema.parse(req.body);
  const table = await prisma.table.create({ data: { ...body, venueId: user.venueId, state: 'FREE' } });
  res.status(201).json(table);
});

const openSessionSchema = z.object({ guests: z.number().int().positive().default(1) });

app.post('/api/v1/orders-tables/tables/:id/sessions', devAuth, requireRoles('OWNER', 'MANAGER', 'WAITER'), async (req: Request, res: Response) => {
  const user = (req as any).devUser as DevUser;
  const id = req.params.id as string;
  const { guests } = openSessionSchema.parse(req.body);
  const table = await prisma.table.findFirst({ where: { id, venueId: user.venueId } });
  if (!table || table.state !== 'FREE') {
    res.status(400).json({ error: 'Table not free' });
    return;
  }
  const session = await prisma.$transaction(async (tx: Tx) => {
    const s = await tx.tableSession.create({ data: { tableId: id, guests } });
    await tx.table.update({ where: { id }, data: { state: 'OCCUPIED' } });
    return s;
  });
  res.status(201).json(session);
});

app.get('/api/v1/orders-tables/sessions/:id/orders', devAuth, async (req: Request, res: Response) => {
  const id = req.params.id as string;
  const orders = await prisma.order.findMany({
    where: { sessionId: id },
    include: { items: { include: { product: true } } },
    orderBy: { createdAt: 'desc' },
  });
  res.json(orders);
});

app.get('/api/v1/orders-tables/orders', devAuth, async (req: Request, res: Response) => {
  const user = (req as any).devUser as DevUser;
  const status = (req.query.status as string | undefined) ?? undefined;
  const orders = await prisma.order.findMany({
    where: { session: { table: { venueId: user.venueId } }, ...(status ? { status } : {}) },
    include: { items: { include: { product: true } }, session: { include: { table: true } } },
    orderBy: { createdAt: 'desc' },
  });
  res.json(orders);
});

app.get('/api/v1/products', devAuth, async (req: Request, res: Response) => {
  const user = (req as any).devUser as DevUser;
  const products = await prisma.product.findMany({ where: { venueId: user.venueId }, include: { stock: true } });
  res.json(products);
});

// --- Moduli ottimizzati (dashboard proprietario) ---
registerOrderRoutes(app, prisma, deps); // creazione ordini con station + timestamp, board per postazione, stato riga
registerStatsRoutes(app, prisma, deps); // statistiche tempi di preparazione
registerCreditRoutes(app, prisma, deps); // crediti clienti in cassa
registerInventoryRoutes(app, prisma, deps); // magazzino: movimenti storicizzati, rettifiche, low stock
registerSupplierRoutes(app, prisma, deps); // fornitori: anagrafica, listino, proposte di riordino
registerPurchaseRoutes(app, prisma, deps); // ordini d'acquisto: ciclo bozza->inviato->ricevuto + ricezione merce

const errorHandler = (err: any, _req: Request, res: Response, _next: NextFunction) => {
  if (err instanceof z.ZodError) {
    res.status(400).json({ error: 'Validation error', issues: err.issues });
    return;
  }
  if (err instanceof Prisma.PrismaClientKnownRequestError) {
    res.status(400).json({ error: err.message, code: err.code });
    return;
  }
  console.error(err);
  res.status(500).json({ error: 'Internal server error' });
};
app.use(errorHandler);

const PORT = process.env.PORT || 3000;
app.listen(PORT, () => console.log(`API listening on port ${PORT}`));

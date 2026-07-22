import type { Express, Request, Response } from 'express';
import type { PrismaClient, Prisma } from '@prisma/client';
import { z } from 'zod';
import { currentUser, type RouteDeps } from '../http';
import { applyTransaction, type CreditTxType } from './credit.logic';

type Tx = Prisma.TransactionClient;

// Ruoli abilitati alla gestione crediti in cassa.
const CASSA_ROLES = ['OWNER', 'MANAGER', 'CASHIER'];

export function registerCreditRoutes(app: Express, prisma: PrismaClient, deps: RouteDeps): void {
  const { devAuth, requireRoles } = deps;

  // ---- Anagrafica: inserimento manuale del cliente creditore in cassa ----
  const createCustomerSchema = z.object({
    name: z.string().min(1),
    phone: z.string().optional(),
    email: z.string().email().optional(),
    notes: z.string().optional(),
    limitCents: z.number().int().nonnegative().default(0),
    openingBalanceCents: z.number().int().nonnegative().default(0), // debito pregresso opzionale
  });

  app.post('/api/v1/credit/customers', devAuth, requireRoles(...CASSA_ROLES), async (req: Request, res: Response) => {
    const user = currentUser(req);
    const body = createCustomerSchema.parse(req.body);

    const customer = await prisma.$transaction(async (tx: Tx) => {
      const c = await tx.customer.create({
        data: {
          venueId: user.venueId,
          name: body.name,
          phone: body.phone,
          email: body.email,
          notes: body.notes,
          limitCents: body.limitCents,
          balanceCents: body.openingBalanceCents,
        },
      });
      if (body.openingBalanceCents > 0) {
        await tx.creditTransaction.create({
          data: {
            customerId: c.id,
            type: 'CHARGE',
            amountCents: body.openingBalanceCents,
            balanceAfterCents: body.openingBalanceCents,
            note: 'Saldo iniziale (inserimento manuale)',
            createdBy: user.userId,
          },
        });
      }
      return c;
    });

    res.status(201).json(customer);
  });

  // ---- Elenco clienti con saldo (opz. solo con debito) ----
  app.get('/api/v1/credit/customers', devAuth, requireRoles(...CASSA_ROLES), async (req: Request, res: Response) => {
    const user = currentUser(req);
    const onlyDebtors = req.query.debtors === 'true';
    const search = (req.query.q as string | undefined)?.trim();

    const customers = await prisma.customer.findMany({
      where: {
        venueId: user.venueId,
        active: true,
        ...(onlyDebtors ? { balanceCents: { gt: 0 } } : {}),
        ...(search ? { name: { contains: search, mode: 'insensitive' } } : {}),
      },
      orderBy: [{ balanceCents: 'desc' }, { name: 'asc' }],
    });

    const totalOutstanding = customers.reduce((s, c) => s + Math.max(0, c.balanceCents), 0);
    res.json({ customers, totalOutstandingCents: totalOutstanding });
  });

  // ---- Dettaglio + estratto conto ----
  app.get('/api/v1/credit/customers/:id', devAuth, requireRoles(...CASSA_ROLES), async (req: Request, res: Response) => {
    const user = currentUser(req);
    const id = req.params.id as string;
    const customer = await prisma.customer.findFirst({ where: { id, venueId: user.venueId } });
    if (!customer) {
      res.status(404).json({ error: 'Cliente non trovato' });
      return;
    }
    const transactions = await prisma.creditTransaction.findMany({
      where: { customerId: id },
      orderBy: { createdAt: 'desc' },
      take: 100,
    });
    res.json({ customer, transactions });
  });

  // ---- Movimento credito: addebito / pagamento / rettifica ----
  const txSchema = z.object({
    type: z.enum(['CHARGE', 'PAYMENT', 'ADJUST']),
    amountCents: z.number().int(), // ADJUST può essere negativo
    orderId: z.string().optional(),
    method: z.enum(['CASH', 'POS']).optional(),
    note: z.string().optional(),
  });

  app.post('/api/v1/credit/customers/:id/transactions', devAuth, requireRoles(...CASSA_ROLES), async (req: Request, res: Response) => {
    const user = currentUser(req);
    const id = req.params.id as string;
    const body = txSchema.parse(req.body);

    try {
      const result = await prisma.$transaction(async (tx: Tx) => {
        const customer = await tx.customer.findFirst({ where: { id, venueId: user.venueId } });
        if (!customer) throw new HttpError(404, 'Cliente non trovato');

        const applied = applyTransaction({
          currentBalanceCents: customer.balanceCents,
          limitCents: customer.limitCents,
          type: body.type as CreditTxType,
          amountCents: body.amountCents,
        });
        if (!applied.ok) throw new HttpError(409, applied.error ?? 'Operazione non consentita');

        const transaction = await tx.creditTransaction.create({
          data: {
            customerId: id,
            type: body.type,
            amountCents: Math.abs(body.amountCents),
            balanceAfterCents: applied.newBalanceCents,
            orderId: body.orderId,
            method: body.method,
            note: body.note,
            createdBy: user.userId,
          },
        });
        const updated = await tx.customer.update({
          where: { id },
          data: { balanceCents: applied.newBalanceCents },
        });
        return { customer: updated, transaction };
      });
      res.status(201).json(result);
    } catch (e) {
      if (e instanceof HttpError) {
        res.status(e.status).json({ error: e.message });
        return;
      }
      throw e;
    }
  });

  // ---- Aggiorna anagrafica / limite / disattiva ----
  const updateSchema = z.object({
    name: z.string().min(1).optional(),
    phone: z.string().optional(),
    email: z.string().email().optional(),
    notes: z.string().optional(),
    limitCents: z.number().int().nonnegative().optional(),
    active: z.boolean().optional(),
  });

  app.patch('/api/v1/credit/customers/:id', devAuth, requireRoles(...CASSA_ROLES), async (req: Request, res: Response) => {
    const user = currentUser(req);
    const id = req.params.id as string;
    const body = updateSchema.parse(req.body);
    const existing = await prisma.customer.findFirst({ where: { id, venueId: user.venueId } });
    if (!existing) {
      res.status(404).json({ error: 'Cliente non trovato' });
      return;
    }
    const updated = await prisma.customer.update({ where: { id }, data: body });
    res.json(updated);
  });
}

class HttpError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

import type { Request, Response, NextFunction, RequestHandler } from 'express';

/** Utente dev iniettato da devAuth (header x-venue-id / x-user-id / x-user-roles). */
export interface DevUser {
  venueId: string;
  userId: string;
  roles: string[];
}

export function currentUser(req: Request): DevUser {
  return (req as any).devUser as DevUser;
}

/**
 * Dipendenze condivise passate ai moduli route così da riusare lo stesso
 * middleware di auth definito nell'entrypoint (`index.ts`).
 */
export interface RouteDeps {
  devAuth: RequestHandler;
  requireRoles: (...allowed: string[]) => RequestHandler;
}

export type { Request, Response, NextFunction };

export class ApiError extends Error {
  status: number;
  detail: string;
  requestId?: string;
  url?: string;

  constructor(status: number, detail: string, requestId?: string, url?: string) {
    super(detail);
    this.name = 'ApiError';
    this.status = status;
    this.detail = detail;
    this.requestId = requestId;
    this.url = url;
  }

  get isNotFound(): boolean { return this.status === 404; }
  get isConflict(): boolean { return this.status === 409; }
  get isValidation(): boolean { return this.status === 422; }
  get isRateLimited(): boolean { return this.status === 429; }
  get isServer(): boolean { return this.status >= 500; }
  get isNetwork(): boolean { return this.status === 0; }

  get userMessage(): string {
    if (this.isNetwork) return 'Impossibile connettersi al server. Verificare che il backend sia attivo.';
    if (this.isRateLimited) return 'Troppe richieste. Attendere qualche secondo prima di riprovare.';
    if (this.isNotFound) return 'Risorsa non trovata.';
    if (this.isConflict) return 'Operazione già in corso.';
    if (this.isValidation) return 'Dati non validi: ' + this.detail;
    if (this.isServer) return 'Errore del server. Riprovare più tardi.';
    return this.detail || `Errore HTTP ${this.status}`;
  }
}

export class TimeoutError extends Error {
  url: string;
  constructor(url: string) {
    super('Richiesta scaduta per timeout');
    this.name = 'TimeoutError';
    this.url = url;
  }
}

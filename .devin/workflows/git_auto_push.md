---
description: Auto-push ogni modifica file su GitHub
---

# Regola di lavoro — push automatico su Git

Dopo **ogni modifica significativa** a file di codice, configurazione o documentazione nel workspace, eseguire immediatamente:

1. Verificare lo stato con `git status --short`.
2. Aggiungere tutte le modifiche: `git add -A`.
3. Creare un commit descrittivo: `git commit -m "<descrizione chiara della modifica>"`.
4. Pushare sul branch remoto: `git push origin main`.

## Note

- Il repository remoto e' `origin` sul branch `main`.
- Il token GitHub e' salvato in `.env` come `GITHUB_TOKEN`; non deve essere incluso nel commit (`.env` e in `.gitignore`).
- Se il push richiede autenticazione, configurare l'URL remoto temporaneo con il PAT oppure usare Git Credential Manager.
- Non aspettare la fine della sessione: ogni fix/feature deve essere versionato subito.
- Se un commit isolerebbe il codice in uno stato non funzionante, preferire commit atomici ma coerenti; in caso di modifiche intermedie fragili, raggruppare in un unico commit prima del push.

## Comandi di riferimento (PowerShell)

```powershell
& "C:\Program Files\Git\bin\git.exe" status --short
& "C:\Program Files\Git\bin\git.exe" add -A
& "C:\Program Files\Git\bin\git.exe" commit -m "descrizione modifica"
& "C:\Program Files\Git\bin\git.exe" push origin main
```

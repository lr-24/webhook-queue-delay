# Cronologia dei rami di questo fork

Fork `lr-24/webhook-queue-delay`: riceve il webhook «nuova transazione» di Firefly III, aspetta e poi chiede a Firefly
di lanciare un altro webhook per quella transazione, una chiamata alla volta (nel server di casa: il webhook 4 verso il
categorizzatore).

Ultimo aggiornamento: 2026-10-10.

Schema dei nomi dei rami nuovi: `NN-AAAA-MM-GG-descrizione` (numero d'ordine, data dell'ultimo commit). I rami già
esistenti non sono stati rinominati; `main` non si rinomina.

| N. | Ramo | Ultimo commit | Cosa contiene |
|---|---|---|---|
| – | `main` | 2024-08-14 | base del fork |
| 01 | `celery` | 2024-08-14 | prova con Celery (4 commit su `main`), non in uso |
| 02 | `worker` | 2024-08-15 | coda in memoria con un solo thread: attende 30 secondi, almeno 29 tra due chiamate (6 commit su `main`); **in uso sul server fino al 2026-10-10** |
| 03 | `03-2026-10-10-coda-persistente-con-nuovi-tentativi` | 2026-10-10 | la coda viene salvata su file e sopravvive ai riavvii; nuovi tentativi dopo 1 min, 5 min, 15 min, 1 h, 6 h; dopo l'ultimo la transazione va nell'elenco delle «abbandonate» e il log scrive `Giving up on transaction`; la stessa transazione non entra due volte in coda; timeout di 30 secondi su ogni chiamata; una risposta 404 (transazione sparita) non viene ritentata; `GET /health` mostra transazioni in attesa, la più vecchia e quelle abbandonate |

## Ramo 03: impostazioni

Variabili d'ambiente (con il valore predefinito): `QUEUE_FILE` (`/data/queue.json`: va montata come volume,
altrimenti la coda si perde ancora a ogni ricreazione del container), `WAIT_BEFORE_PROCESSING` (30), `MIN_DELAY_BETWEEN_CALLS` (29),
`RETRY_DELAYS` (`60,300,900,3600,21600`, in secondi), `REQUEST_TIMEOUT` (30), `LOG_FILE` (`/app/logs/app.log`).

I messaggi del log restano quelli del ramo `worker` (`API response for transaction N: Status NNN`, `API request failed ...`)
più `... trying again in N seconds` e `Giving up on transaction N`.

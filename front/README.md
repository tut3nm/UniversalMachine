# front

Frontend del sistema web (React + TypeScript + Vite) que reemplaza las apps
de escritorio `máquina232` (Configurador de Planta) y `Diagramadora`
(Conversor de Mediciones), ya migradas. Ver [`PLAN_WEBAPP.md`](../PLAN_WEBAPP.md)
en la raíz para la arquitectura completa.

## Desarrollo

```
npm install
npm run dev
```

Requiere el backend corriendo aparte (`cd ../backend && py -m uvicorn app.main:app --reload`), en `http://127.0.0.1:8000` por default — ver `src/api.ts`.

## Build para empaquetar

```
npm run build
```

Genera `dist/`, que `backend/app/main.py` sirve como estáticos cuando existe (modo empaquetado/pywebview).

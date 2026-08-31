# front

Frontend del nuevo sistema web (React + TypeScript + Vite) que unifica
`máquina232` (Configurador de Planta) y `Diagramadora` (Conversor de
Mediciones). Ver [`PLAN_WEBAPP.md`](../PLAN_WEBAPP.md) en la raíz para la
arquitectura completa. `máquina232/` y `Diagramadora/` (las apps de
escritorio existentes) no dependen de esta carpeta y siguen usándose tal
cual mientras se construye esto.

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

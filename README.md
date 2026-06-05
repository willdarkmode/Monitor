# Sankhya Dashboard Comercial

Dashboard local para TV com dados de estoque, faturamento, metas e ranking comercial.

## Como rodar

```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
# Linux/Mac
source .venv/bin/activate

pip install -r requirements.txt
copy .env.example .env  # Windows
# ou: cp .env.example .env

uvicorn app:app --reload --host 0.0.0.0 --port 8000
```

Abra no navegador:

```text
http://localhost:8000/tv
```

Na TV, use:

```text
http://IP-DA-MAQUINA:8000/tv
```

## Usar dados reais

Edite o `.env`:

```env
DASHBOARD_USAR_MOCK=false
SANKHYA_USUARIO=...
SANKHYA_SENHA=...
SANKHYA_BASE_URL=...
SANKHYA_SESSAO_ESTOQUE=...
SANKHYA_SESSAO_FATURAMENTO=...
META_BASE=3750000
SUPER_META=4000000
```

## Rotas

- `/tv` - dashboard para televisão
- `/api/dashboard` - JSON com dados atuais
- `/api/refresh` - força atualização dos dados

FROM python:3.12-slim AS backend
WORKDIR /app/backend
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/ .
EXPOSE 8001
CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8001"]

FROM node:24-alpine AS frontend-build
WORKDIR /app/frontend
COPY frontend/package.json frontend/yarn.lock ./
RUN yarn install --frozen-lockfile
COPY frontend/ .
ARG FRONTEND_API_URL=""
ENV VITE_API_URL=$FRONTEND_API_URL
RUN yarn build

FROM node:24-alpine
WORKDIR /app
RUN apk add --no-cache mongodb-tools
COPY --from=frontend-build /app/frontend/dist ./frontend/dist
COPY --from=backend /usr/local/lib/python3.12/site-packages ./pylib
COPY --from=backend /usr/local/bin ./pybin
COPY docker/serve.py ./serve.py
EXPOSE 3000 8001
CMD ["sh", "-c", "python serve.py"]

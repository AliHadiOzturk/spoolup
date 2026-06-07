FROM node:20-alpine

WORKDIR /app

# NOTE: Must include /api path since all backend routes are prefixed with /api
# Production example: https://api.yourdomain.com/api
ARG VITE_API_URL=http://localhost:8000/api
ENV VITE_API_URL=${VITE_API_URL}

COPY package*.json pnpm-lock.yaml ./

RUN npm install -g pnpm && pnpm install

COPY . .

RUN npx vite build

RUN npm install -g serve

EXPOSE 3000

CMD ["serve", "-s", "dist", "-l", "3000"]

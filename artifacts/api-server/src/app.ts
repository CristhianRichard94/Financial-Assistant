import express, { type Express, type NextFunction, type Request, type Response } from "express";
import cors from "cors";
import multer from "multer";
import pinoHttp from "pino-http";
import router from "./routes";
import { logger } from "./lib/logger";

const app: Express = express();

app.use(
  pinoHttp({
    logger,
    serializers: {
      req(req) {
        return {
          id: req.id,
          method: req.method,
          url: req.url?.split("?")[0],
        };
      },
      res(res) {
        return {
          statusCode: res.statusCode,
        };
      },
    },
  }),
);
app.use(cors());
app.use(express.json());
app.use(express.urlencoded({ extended: true }));

app.use("/api", router);

// Catch-all error handler. Registered last so it receives any error passed to
// `next(err)` by upstream middleware/routes (e.g. multer file-size limits) or
// bubbled up by Express itself. This is the only safety net against Express's
// default error handler, which would otherwise leak raw stack traces and
// internal file paths to clients.
app.use((err: unknown, req: Request, res: Response, _next: NextFunction) => {
  if (err instanceof multer.MulterError && err.code === "LIMIT_FILE_SIZE") {
    res.status(400).json({ error: "File exceeds 10MB limit" });
    return;
  }

  req.log?.error({ err }, "Unhandled error");
  res.status(500).json({ error: "Internal server error" });
});

export default app;

import express from "express";
import compression from "compression";
import { fileURLToPath } from "url";
import { dirname, join } from "path";

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

const app = express();
app.use(compression());
app.use(express.static(join(__dirname, "dist")));  // serve built files

// SPA fallback (so /about etc. work on refresh)
app.get("*", (_, res) => {
  res.sendFile(join(__dirname, "dist", "index.html"));
});

const port = process.env.PORT || 8080;
app.listen(port, "0.0.0.0", () => {
  console.log(`Listening on http://0.0.0.0:${port}`);
});
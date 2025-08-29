import { Redis } from "@upstash/redis";

const redis = new Redis({
  url: process.env.UPSTASH_REDIS_REST_URL,
  token: process.env.UPSTASH_REDIS_REST_TOKEN,
});

export default async function handler(req, res) {
  const now = Math.floor(Date.now() / 1000);

  // --- POST: from Unity client
  if (req.method === "POST") {
    if (
      process.env.MONKE_API_KEY &&
      req.headers["x-api-key"] !== process.env.MONKE_API_KEY
    ) {
      return res.status(401).json({ error: "unauthorized" });
    }

    const body = req.body;
    let count = parseInt(body.player_count, 10);
    if (isNaN(count)) return res.status(400).json({ error: "player_count required" });

    const snapshot = {
      player_count: count,
      room_name: body.room_name || "",
      game_version: body.game_version || "",
      game_name: body.game_name || "",
      timestamp: now,
    };

    // Store timeseries (ZADD) and trim >24h old
    await redis.zadd("monke:series", { score: now, member: JSON.stringify({ t: now, c: count }) });
    await redis.zremrangebyscore("monke:series", "-inf", now - 24 * 3600);

    // Store current snapshot (hash-like, but use JSON)
    await redis.set("monke:current", JSON.stringify(snapshot));

    return res.json({ ok: true });
  }

  // --- GET: return stats
  if (req.method === "GET") {
    const seriesRaw = await redis.zrange("monke:series", 0, -1);
    const series = seriesRaw.map((s) => JSON.parse(s));
    const peak = series.reduce((m, pt) => Math.max(m, pt.c), 0);

    const currRaw = await redis.get("monke:current");
    const current = currRaw ? JSON.parse(currRaw) : {};

    return res.json({
      current,
      peak_24h: peak,
      last_24h: series,
    });
  }

  res.setHeader("Allow", ["GET", "POST"]);
  res.status(405).end(`Method ${req.method} Not Allowed`);
}

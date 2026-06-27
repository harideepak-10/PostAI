exports.handler = async (event) => {
  // Handle CORS preflight
  if (event.httpMethod === "OPTIONS") {
    return {
      statusCode: 200,
      headers: {
        "Access-Control-Allow-Origin":  "*",
        "Access-Control-Allow-Headers": "Content-Type",
        "Access-Control-Allow-Methods": "POST, OPTIONS",
      },
      body: "",
    };
  }

  if (event.httpMethod !== "POST") {
    return { statusCode: 405, body: "Method not allowed" };
  }

  let body;
  try {
    body = JSON.parse(event.body);
  } catch {
    return { statusCode: 400, body: "Invalid JSON" };
  }

  const { igAccountId, pageToken, caption, imageBase64 } = body;

  if (!igAccountId || !pageToken || !caption || !imageBase64) {
    return {
      statusCode: 400,
      headers: { "Access-Control-Allow-Origin": "*" },
      body: JSON.stringify({ error: "Missing required fields" }),
    };
  }

  const IMGBB_KEY = process.env.IMGBB_API_KEY;
  if (!IMGBB_KEY) {
    return {
      statusCode: 500,
      headers: { "Access-Control-Allow-Origin": "*" },
      body: JSON.stringify({ error: "IMGBB_API_KEY not set in environment" }),
    };
  }

  try {
    // ── Step 1: Upload image to ImgBB to get a public HTTPS URL ────────────
    // Instagram Graph API requires a publicly accessible image URL
    const imgbbParams = new URLSearchParams({
      key:        IMGBB_KEY,
      image:      imageBase64,
      expiration: "600", // auto-delete after 10 minutes
    });

    const imgbbRes = await fetch("https://api.imgbb.com/1/upload", {
      method:  "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body:    imgbbParams.toString(),
    });
    const imgbbData = await imgbbRes.json();

    if (!imgbbData.success) {
      return {
        statusCode: 500,
        headers: { "Access-Control-Allow-Origin": "*" },
        body: JSON.stringify({ error: "Image hosting failed", detail: imgbbData }),
      };
    }

    const imageUrl = imgbbData.data.url;

    // ── Step 2: Create Instagram media container ────────────────────────────
    const containerRes = await fetch(
      `https://graph.facebook.com/v19.0/${igAccountId}/media`,
      {
        method:  "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          image_url:    imageUrl,
          caption:      caption,
          access_token: pageToken,
        }),
      }
    );
    const containerData = await containerRes.json();

    if (!containerData.id) {
      return {
        statusCode: 400,
        headers: { "Access-Control-Allow-Origin": "*" },
        body: JSON.stringify({
          error: containerData.error ? containerData.error.message : "Container creation failed",
          detail: containerData,
        }),
      };
    }

    // ── Step 3: Publish the container ──────────────────────────────────────
    const publishRes = await fetch(
      `https://graph.facebook.com/v19.0/${igAccountId}/media_publish`,
      {
        method:  "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          creation_id:  containerData.id,
          access_token: pageToken,
        }),
      }
    );
    const publishData = await publishRes.json();

    if (publishData.id) {
      return {
        statusCode: 200,
        headers: { "Access-Control-Allow-Origin": "*" },
        body: JSON.stringify({ success: true, postId: publishData.id }),
      };
    }

    return {
      statusCode: 400,
      headers: { "Access-Control-Allow-Origin": "*" },
      body: JSON.stringify({
        error: publishData.error ? publishData.error.message : "Publish failed",
        detail: publishData,
      }),
    };

  } catch (err) {
    console.error("Instagram post error:", err);
    return {
      statusCode: 500,
      headers: { "Access-Control-Allow-Origin": "*" },
      body: JSON.stringify({ error: err.message }),
    };
  }
};

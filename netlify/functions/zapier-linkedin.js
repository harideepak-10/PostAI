exports.handler = async (event) => {
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

  const { caption, imageBase64 } = body;
  if (!caption) {
    return {
      statusCode: 400,
      headers: { "Access-Control-Allow-Origin": "*" },
      body: JSON.stringify({ error: "Missing caption" }),
    };
  }

  const ZAPIER_URL  = process.env.ZAPIER_LINKEDIN_WEBHOOK;
  const IMGBB_KEY   = process.env.IMGBB_API_KEY;

  if (!ZAPIER_URL) {
    return {
      statusCode: 500,
      headers: { "Access-Control-Allow-Origin": "*" },
      body: JSON.stringify({ error: "ZAPIER_LINKEDIN_WEBHOOK not set in environment" }),
    };
  }

  try {
    let imageUrl = "";

    // Upload image to ImgBB to get a public URL (optional — skipped if no key or image)
    if (imageBase64 && IMGBB_KEY) {
      const imgbbParams = new URLSearchParams({
        key:        IMGBB_KEY,
        image:      imageBase64,
        expiration: "3600",
      });
      const imgbbRes  = await fetch("https://api.imgbb.com/1/upload", {
        method:  "POST",
        headers: { "Content-Type": "application/x-www-form-urlencoded" },
        body:    imgbbParams.toString(),
      });
      const imgbbData = await imgbbRes.json();
      if (imgbbData.success) imageUrl = imgbbData.data.url;
    }

    // Send to Zapier webhook
    const zapRes = await fetch(ZAPIER_URL, {
      method:  "POST",
      headers: { "Content-Type": "application/json" },
      body:    JSON.stringify({ caption, imageUrl }),
    });

    const zapData = await zapRes.json();

    if (zapData.status === "success") {
      return {
        statusCode: 200,
        headers: { "Access-Control-Allow-Origin": "*" },
        body: JSON.stringify({ success: true }),
      };
    }

    return {
      statusCode: 400,
      headers: { "Access-Control-Allow-Origin": "*" },
      body: JSON.stringify({ error: "Zapier rejected the request", detail: zapData }),
    };

  } catch (err) {
    console.error("Zapier LinkedIn error:", err);
    return {
      statusCode: 500,
      headers: { "Access-Control-Allow-Origin": "*" },
      body: JSON.stringify({ error: err.message }),
    };
  }
};

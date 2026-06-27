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

  const { pageToken, pageId, caption, imageBase64, imageType } = body;

  if (!pageToken || !pageId || !caption || !imageBase64) {
    return {
      statusCode: 400,
      headers: { "Access-Control-Allow-Origin": "*" },
      body: JSON.stringify({ error: "Missing required fields" }),
    };
  }

  try {
    const mimeType    = "image/" + (imageType || "jpeg");
    const imageBuffer = Buffer.from(imageBase64, "base64");

    // Build multipart/form-data manually (Node 18 FormData + Blob)
    const { Blob } = require("buffer");
    const formData = new FormData();
    formData.append(
      "source",
      new Blob([imageBuffer], { type: mimeType }),
      "image." + (imageType || "jpg")
    );
    formData.append("caption",      caption);
    formData.append("access_token", pageToken);

    const postRes = await fetch(
      `https://graph.facebook.com/v19.0/${pageId}/photos`,
      { method: "POST", body: formData }
    );

    const postData = await postRes.json();

    if (postData.id || postData.post_id) {
      return {
        statusCode: 200,
        headers: { "Access-Control-Allow-Origin": "*" },
        body: JSON.stringify({ success: true, postId: postData.id || postData.post_id }),
      };
    }

    // Surface the Facebook API error clearly
    const errMsg = postData.error
      ? postData.error.message
      : JSON.stringify(postData);

    return {
      statusCode: 400,
      headers: { "Access-Control-Allow-Origin": "*" },
      body: JSON.stringify({ error: errMsg, detail: postData }),
    };

  } catch (err) {
    console.error("Facebook post error:", err);
    return {
      statusCode: 500,
      headers: { "Access-Control-Allow-Origin": "*" },
      body: JSON.stringify({ error: err.message }),
    };
  }
};

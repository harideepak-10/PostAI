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

  const { token, caption, imageBase64, imageType } = body;

  if (!token || !caption || !imageBase64) {
    return { statusCode: 400, body: "Missing token, caption or image" };
  }

  const authHeader = { Authorization: "Bearer " + token };

  try {
    // ── Step 1: Get author URN ──────────────────────────────────────────────
    const profileRes = await fetch("https://api.linkedin.com/v2/userinfo", {
      headers: authHeader,
    });
    const profile = await profileRes.json();

    if (!profile.sub) {
      return {
        statusCode: 401,
        headers: { "Access-Control-Allow-Origin": "*" },
        body: JSON.stringify({ error: "Invalid token — please reconnect LinkedIn" }),
      };
    }

    const authorUrn = "urn:li:person:" + profile.sub;

    // ── Step 2: Register image upload ───────────────────────────────────────
    const registerRes = await fetch(
      "https://api.linkedin.com/v2/assets?action=registerUpload",
      {
        method:  "POST",
        headers: { ...authHeader, "Content-Type": "application/json" },
        body: JSON.stringify({
          registerUploadRequest: {
            recipes: ["urn:li:digitalmediaRecipe:feedshare-image"],
            owner:   authorUrn,
            serviceRelationships: [{
              relationshipType: "OWNER",
              identifier: "urn:li:userGeneratedContent",
            }],
          },
        }),
      }
    );

    const registerData = await registerRes.json();
    const uploadUrl = registerData.value
      .uploadMechanism["com.linkedin.digitalmedia.uploading.MediaUploadHttpRequest"]
      .uploadUrl;
    const assetUrn = registerData.value.asset;

    // ── Step 3: Upload image bytes ──────────────────────────────────────────
    const imageBuffer = Buffer.from(imageBase64, "base64");
    await fetch(uploadUrl, {
      method:  "PUT",
      headers: { "Content-Type": "application/octet-stream" },
      body:    imageBuffer,
    });

    // ── Step 4: Create the post ─────────────────────────────────────────────
    const postRes = await fetch("https://api.linkedin.com/v2/ugcPosts", {
      method:  "POST",
      headers: {
        ...authHeader,
        "Content-Type": "application/json",
        "X-Restli-Protocol-Version": "2.0.0",
      },
      body: JSON.stringify({
        author:         authorUrn,
        lifecycleState: "PUBLISHED",
        specificContent: {
          "com.linkedin.ugc.ShareContent": {
            shareCommentary:   { text: caption },
            shareMediaCategory: "IMAGE",
            media: [{
              status:      "READY",
              description: { text: caption.substring(0, 200) },
              media:       assetUrn,
            }],
          },
        },
        visibility: {
          "com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC",
        },
      }),
    });

    const postData = await postRes.json();

    if (postData.id) {
      return {
        statusCode: 200,
        headers: { "Access-Control-Allow-Origin": "*" },
        body: JSON.stringify({ success: true, postId: postData.id }),
      };
    } else {
      return {
        statusCode: 400,
        headers: { "Access-Control-Allow-Origin": "*" },
        body: JSON.stringify({ error: postData.message || "Post failed", detail: postData }),
      };
    }

  } catch (err) {
    console.error("LinkedIn post error:", err);
    return {
      statusCode: 500,
      headers: { "Access-Control-Allow-Origin": "*" },
      body: JSON.stringify({ error: err.message }),
    };
  }
};

exports.handler = async (event) => {
  const { code, error } = event.queryStringParameters || {};

  if (error) {
    return {
      statusCode: 302,
      headers: { Location: "/?li_error=" + encodeURIComponent(error) }
    };
  }

  if (!code) {
    return { statusCode: 400, body: "Missing code" };
  }

  const CLIENT_ID     = process.env.LINKEDIN_CLIENT_ID;
  const CLIENT_SECRET = process.env.LINKEDIN_CLIENT_SECRET;
  const REDIRECT_URI  = process.env.LINKEDIN_REDIRECT_URI;

  try {
    // Exchange auth code for access token
    const params = new URLSearchParams({
      grant_type:    "authorization_code",
      code,
      redirect_uri:  REDIRECT_URI,
      client_id:     CLIENT_ID,
      client_secret: CLIENT_SECRET,
    });

    const tokenRes = await fetch("https://www.linkedin.com/oauth/v2/accessToken", {
      method:  "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body:    params.toString(),
    });

    const tokenData = await tokenRes.json();

    if (!tokenData.access_token) {
      return {
        statusCode: 302,
        headers: { Location: "/?li_error=token_failed" }
      };
    }

    // Redirect back to app with token in hash (never in server logs)
    return {
      statusCode: 302,
      headers: {
        Location: `/#li_token=${encodeURIComponent(tokenData.access_token)}&li_expires=${tokenData.expires_in || 5183944}`
      }
    };

  } catch (err) {
    console.error("LinkedIn auth error:", err);
    return {
      statusCode: 302,
      headers: { Location: "/?li_error=server_error" }
    };
  }
};

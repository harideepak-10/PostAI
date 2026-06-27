exports.handler = async (event) => {
  const { code, error } = event.queryStringParameters || {};

  if (error) {
    return {
      statusCode: 302,
      headers: { Location: "/?fb_error=" + encodeURIComponent(error) },
    };
  }

  if (!code) return { statusCode: 400, body: "Missing code" };

  const APP_ID      = process.env.FACEBOOK_APP_ID;
  const APP_SECRET  = process.env.FACEBOOK_APP_SECRET;
  const REDIRECT_URI = process.env.FACEBOOK_REDIRECT_URI;

  try {
    // ── Step 1: Exchange auth code for user access token ────────────────────
    const tokenRes = await fetch(
      `https://graph.facebook.com/v19.0/oauth/access_token` +
      `?client_id=${APP_ID}` +
      `&redirect_uri=${encodeURIComponent(REDIRECT_URI)}` +
      `&client_secret=${APP_SECRET}` +
      `&code=${code}`
    );
    const tokenData = await tokenRes.json();

    if (!tokenData.access_token) {
      console.error("Token exchange failed:", tokenData);
      return {
        statusCode: 302,
        headers: { Location: "/?fb_error=token_failed" },
      };
    }

    const userToken = tokenData.access_token;

    // ── Step 2: Get user's Facebook Pages ──────────────────────────────────
    const pagesRes = await fetch(
      `https://graph.facebook.com/v19.0/me/accounts?access_token=${userToken}`
    );
    const pagesData = await pagesRes.json();

    if (!pagesData.data || pagesData.data.length === 0) {
      return {
        statusCode: 302,
        headers: { Location: "/?fb_error=no_pages" },
      };
    }

    // Use the first page (user can only have one connected at a time for now)
    const page      = pagesData.data[0];
    const pageId    = page.id;
    const pageToken = page.access_token; // long-lived page token

    // ── Step 3: Get Instagram Business Account linked to this page ──────────
    const igRes = await fetch(
      `https://graph.facebook.com/v19.0/${pageId}` +
      `?fields=instagram_business_account&access_token=${pageToken}`
    );
    const igData = await igRes.json();
    const igId = igData.instagram_business_account
      ? igData.instagram_business_account.id
      : "";

    // ── Step 4: Redirect back with all tokens in URL hash ───────────────────
    const params = new URLSearchParams({
      fb_token:   pageToken,
      fb_page_id: pageId,
      fb_ig_id:   igId,
    });

    return {
      statusCode: 302,
      headers: { Location: `/#${params.toString()}` },
    };

  } catch (err) {
    console.error("Facebook auth error:", err);
    return {
      statusCode: 302,
      headers: { Location: "/?fb_error=server_error" },
    };
  }
};

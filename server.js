require("dotenv").config();
const express = require("express");
const cors = require("cors");
const axios = require("axios");
const OpenAI = require("openai").default;
const path = require("path");

const app = express();
app.use(cors());
app.use(express.json({ limit: "10mb" }));
app.use(express.static(path.join(__dirname, "public")));

let openai;
function getOpenAI() {
  if (!openai) openai = new OpenAI({ apiKey: process.env.OPENAI_API_KEY });
  return openai;
}

// ─── Generate Poster Image ─────────────────────────────────────────────────
app.post("/api/generate-image", async (req, res) => {
  try {
    const { topic, style } = req.body;
    const prompt = `Create a professional, eye-catching social media poster for: "${topic}". Style: ${style || "modern and vibrant"}. No text overlays, focus on visual imagery that represents the topic powerfully. High quality, suitable for LinkedIn, Instagram, and Facebook.`;

    const response = await getOpenAI().images.generate({
      model: "dall-e-3",
      prompt,
      n: 1,
      size: "1024x1024",
      quality: "standard",
      response_format: "url",
    });

    res.json({ imageUrl: response.data[0].url, revisedPrompt: response.data[0].revised_prompt });
  } catch (err) {
    console.error("Image generation error:", err.message);
    res.status(500).json({ error: err.message });
  }
});

// ─── Generate Captions ─────────────────────────────────────────────────────
app.post("/api/generate-captions", async (req, res) => {
  try {
    const { topic, tone, platforms } = req.body;
    const toneMap = {
      professional: "professional and informative",
      casual: "casual, friendly and conversational",
      inspirational: "motivational and inspiring",
      humorous: "witty and humorous",
      promotional: "compelling and sales-oriented",
    };
    const toneDesc = toneMap[tone] || tone || "professional";

    const completion = await getOpenAI().chat.completions.create({
      model: "gpt-4o",
      messages: [
        {
          role: "system",
          content: `You are a social media expert who writes highly engaging captions. Always return valid JSON only, no markdown.`,
        },
        {
          role: "user",
          content: `Generate social media captions for this topic: "${topic}"
Tone: ${toneDesc}
Platforms requested: ${platforms.join(", ")}

Return a JSON object with keys for each platform. Each value should be a string with the caption optimized for that platform:
- linkedin: Professional tone, up to 3000 chars, include relevant hashtags (5-10), use line breaks for readability
- instagram: Engaging, emoji-rich, up to 2200 chars, 20-30 relevant hashtags at the end
- facebook: Conversational, up to 500 chars, 3-5 hashtags, encourage engagement (ask a question or add CTA)

Only include keys for the platforms in the list: ${platforms.join(", ")}
Return ONLY the JSON object, no explanation.`,
        },
      ],
      temperature: 0.8,
    });

    let captions = {};
    try {
      captions = JSON.parse(completion.choices[0].message.content);
    } catch {
      captions = { raw: completion.choices[0].message.content };
    }

    res.json({ captions });
  } catch (err) {
    console.error("Caption generation error:", err.message);
    res.status(500).json({ error: err.message });
  }
});

// ─── Post to LinkedIn ──────────────────────────────────────────────────────
app.post("/api/post/linkedin", async (req, res) => {
  try {
    const { caption, imageUrl } = req.body;
    const token = process.env.LINKEDIN_ACCESS_TOKEN;
    const personUrn = process.env.LINKEDIN_PERSON_URN;

    if (!token || !personUrn) {
      return res.status(400).json({ error: "LinkedIn credentials not configured in .env" });
    }

    let shareMediaCategory = "NONE";
    let media = [];

    // Upload image to LinkedIn if provided
    if (imageUrl) {
      // Step 1: Register image upload
      const registerRes = await axios.post(
        "https://api.linkedin.com/v2/assets?action=registerUpload",
        {
          registerUploadRequest: {
            recipes: ["urn:li:digitalmediaRecipe:feedshare-image"],
            owner: personUrn,
            serviceRelationships: [{ relationshipType: "OWNER", identifier: "urn:li:userGeneratedContent" }],
          },
        },
        { headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" } }
      );

      const uploadUrl = registerRes.data.value.uploadMechanism["com.linkedin.digitalmedia.uploading.MediaUploadHttpRequest"].uploadUrl;
      const assetUrn = registerRes.data.value.asset;

      // Step 2: Download image and upload to LinkedIn
      const imgResponse = await axios.get(imageUrl, { responseType: "arraybuffer" });
      await axios.put(uploadUrl, imgResponse.data, {
        headers: { Authorization: `Bearer ${token}`, "Content-Type": "image/png" },
      });

      shareMediaCategory = "IMAGE";
      media = [{ status: "READY", description: { text: caption.substring(0, 200) }, media: assetUrn, title: { text: "Post" } }];
    }

    // Step 3: Create the post
    const postBody = {
      author: personUrn,
      lifecycleState: "PUBLISHED",
      specificContent: {
        "com.linkedin.ugc.ShareContent": {
          shareCommentary: { text: caption },
          shareMediaCategory,
          ...(media.length > 0 && { media }),
        },
      },
      visibility: { "com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC" },
    };

    const postRes = await axios.post("https://api.linkedin.com/v2/ugcPosts", postBody, {
      headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json", "X-Restli-Protocol-Version": "2.0.0" },
    });

    res.json({ success: true, postId: postRes.data.id, platform: "linkedin" });
  } catch (err) {
    console.error("LinkedIn post error:", err.response?.data || err.message);
    res.status(500).json({ error: err.response?.data?.message || err.message });
  }
});

// ─── Post to Facebook ──────────────────────────────────────────────────────
app.post("/api/post/facebook", async (req, res) => {
  try {
    const { caption, imageUrl } = req.body;
    const token = process.env.FACEBOOK_PAGE_ACCESS_TOKEN;
    const pageId = process.env.FACEBOOK_PAGE_ID;

    if (!token || !pageId) {
      return res.status(400).json({ error: "Facebook credentials not configured in .env" });
    }

    let postRes;
    if (imageUrl) {
      // Post with photo
      postRes = await axios.post(`https://graph.facebook.com/v19.0/${pageId}/photos`, {
        url: imageUrl,
        caption,
        access_token: token,
      });
    } else {
      // Text-only post
      postRes = await axios.post(`https://graph.facebook.com/v19.0/${pageId}/feed`, {
        message: caption,
        access_token: token,
      });
    }

    res.json({ success: true, postId: postRes.data.id, platform: "facebook" });
  } catch (err) {
    console.error("Facebook post error:", err.response?.data || err.message);
    res.status(500).json({ error: err.response?.data?.error?.message || err.message });
  }
});

// ─── Post to Instagram ─────────────────────────────────────────────────────
app.post("/api/post/instagram", async (req, res) => {
  try {
    const { caption, imageUrl } = req.body;
    const token = process.env.FACEBOOK_PAGE_ACCESS_TOKEN;
    const igAccountId = process.env.INSTAGRAM_ACCOUNT_ID;

    if (!token || !igAccountId) {
      return res.status(400).json({ error: "Instagram credentials not configured in .env" });
    }

    if (!imageUrl) {
      return res.status(400).json({ error: "Instagram requires an image to post" });
    }

    // Step 1: Create media container
    const containerRes = await axios.post(
      `https://graph.facebook.com/v19.0/${igAccountId}/media`,
      { image_url: imageUrl, caption, access_token: token }
    );

    const containerId = containerRes.data.id;

    // Step 2: Poll until container is ready
    let ready = false;
    for (let i = 0; i < 10; i++) {
      await new Promise((r) => setTimeout(r, 3000));
      const statusRes = await axios.get(`https://graph.facebook.com/v19.0/${containerId}`, {
        params: { fields: "status_code", access_token: token },
      });
      if (statusRes.data.status_code === "FINISHED") { ready = true; break; }
      if (statusRes.data.status_code === "ERROR") throw new Error("Instagram media processing failed");
    }

    if (!ready) throw new Error("Instagram media container timed out");

    // Step 3: Publish
    const publishRes = await axios.post(
      `https://graph.facebook.com/v19.0/${igAccountId}/media_publish`,
      { creation_id: containerId, access_token: token }
    );

    res.json({ success: true, postId: publishRes.data.id, platform: "instagram" });
  } catch (err) {
    console.error("Instagram post error:", err.response?.data || err.message);
    res.status(500).json({ error: err.response?.data?.error?.message || err.message });
  }
});

// ─── Health check ──────────────────────────────────────────────────────────
app.get("/api/health", (req, res) => {
  res.json({
    status: "ok",
    configured: {
      openai: !!process.env.OPENAI_API_KEY,
      linkedin: !!(process.env.LINKEDIN_ACCESS_TOKEN && process.env.LINKEDIN_PERSON_URN),
      facebook: !!(process.env.FACEBOOK_PAGE_ACCESS_TOKEN && process.env.FACEBOOK_PAGE_ID),
      instagram: !!(process.env.FACEBOOK_PAGE_ACCESS_TOKEN && process.env.INSTAGRAM_ACCOUNT_ID),
    },
  });
});

const PORT = process.env.PORT || 3000;
app.listen(PORT, () => console.log(`🚀 Social AI Poster running at http://localhost:${PORT}`));

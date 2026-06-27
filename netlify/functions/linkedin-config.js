exports.handler = async () => {
  return {
    statusCode: 200,
    headers: {
      "Content-Type": "application/json",
      "Access-Control-Allow-Origin": "*",
    },
    body: JSON.stringify({
      clientId: process.env.LINKEDIN_CLIENT_ID || "",
    }),
  };
};

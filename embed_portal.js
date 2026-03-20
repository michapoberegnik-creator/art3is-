function buildSpotifyEmbed(url) {
  const match = url.match(/open\.spotify\.com\/(track|album|playlist|artist|episode|show)\/([A-Za-z0-9]+)/i);
  if (!match) return null;
  const [, type, id] = match;
  return {
    src: `https://open.spotify.com/embed/${type}/${id}?utm_source=generator`,
    label: `Spotify ${type}`,
  };
}

function buildYouTubeEmbed(url) {
  let videoId = null;
  let playlistId = null;

  try {
    const parsed = new URL(url);
    if (parsed.hostname.includes("youtu.be")) {
      videoId = parsed.pathname.replace("/", "");
    } else if (parsed.pathname === "/watch") {
      videoId = parsed.searchParams.get("v");
      playlistId = parsed.searchParams.get("list");
    } else if (parsed.pathname.startsWith("/shorts/")) {
      videoId = parsed.pathname.split("/")[2];
    } else if (parsed.pathname === "/playlist") {
      playlistId = parsed.searchParams.get("list");
    }
  } catch (_error) {
    return null;
  }

  if (!videoId && !playlistId) return null;
  const params = new URLSearchParams({ rel: "0", autoplay: "1" });
  let src = "https://www.youtube.com/embed/";
  if (videoId) {
    src += encodeURIComponent(videoId);
    if (playlistId) params.set("list", playlistId);
  } else {
    src += "videoseries";
    params.set("list", playlistId);
  }
  return { src: `${src}?${params.toString()}`, label: "YouTube" };
}

async function buildSoundCloudEmbed(url) {
  try {
    const endpoint = new URL("https://soundcloud.com/oembed");
    endpoint.searchParams.set("format", "json");
    endpoint.searchParams.set("url", url);
    endpoint.searchParams.set("auto_play", "true");
    const response = await fetch(endpoint.toString());
    if (!response.ok) return null;
    const data = await response.json();
    return { html: data.html, label: "SoundCloud" };
  } catch (_error) {
    return null;
  }
}

function setStatus(message) {
  document.getElementById("status").textContent = message;
}

function setEmbedContent(content) {
  const root = document.getElementById("embed-root");
  root.innerHTML = "";
  if (!content) {
    root.textContent = "No media loaded yet.";
    return;
  }
  if (content.html) {
    root.innerHTML = content.html;
    return;
  }
  const iframe = document.createElement("iframe");
  iframe.src = content.src;
  iframe.allow = "autoplay; clipboard-write; encrypted-media; fullscreen; picture-in-picture";
  root.appendChild(iframe);
}

async function loadEmbed(sourceUrl) {
  const trimmed = sourceUrl.trim();
  if (!trimmed) {
    setStatus("Paste an official Spotify, SoundCloud, or YouTube URL.");
    setEmbedContent(null);
    return;
  }

  const spotify = buildSpotifyEmbed(trimmed);
  if (spotify) {
    setEmbedContent(spotify);
    setStatus(`Loaded ${spotify.label} embed.`);
    return;
  }

  const youtube = buildYouTubeEmbed(trimmed);
  if (youtube) {
    setEmbedContent(youtube);
    setStatus("Loaded YouTube embed.");
    return;
  }

  const soundcloud = await buildSoundCloudEmbed(trimmed);
  if (soundcloud) {
    setEmbedContent(soundcloud);
    setStatus("Loaded SoundCloud embed.");
    return;
  }

  setEmbedContent(null);
  setStatus("Unsupported URL. Use an official Spotify, SoundCloud, or YouTube share link.");
}

window.addEventListener("DOMContentLoaded", () => {
  const input = document.getElementById("source-input");
  document.getElementById("load-button").addEventListener("click", () => loadEmbed(input.value));
  document.getElementById("clear-button").addEventListener("click", () => {
    input.value = "";
    setEmbedContent(null);
    setStatus("Waiting for a supported official URL.");
  });

  const initialUrl = new URLSearchParams(window.location.search).get("url");
  if (initialUrl) {
    input.value = initialUrl;
    loadEmbed(initialUrl);
  }
});

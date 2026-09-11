// InlineVideo — embedded YouTube players from the tutor's find_videos.
// Click-to-load: thumbnail + play button until tapped, so no Google request
// fires before the learner chooses to watch.

import { useState } from "react";
import { BadgeCheck, Play } from "lucide-react";
import type { ChatMessage, VideoItem } from "../api";
import { cardPayload } from "../api";

function VideoCard({ video }: { video: VideoItem }) {
  const [playing, setPlaying] = useState(false);
  return (
    <div className="rounded-xl overflow-hidden bg-black/40 border border-border/60">
      {playing ? (
        <iframe
          src={`${video.embed_url}?autoplay=1&rel=0`}
          title={video.title}
          allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
          allowFullScreen
          className="w-full aspect-video"
        />
      ) : (
        <button
          onClick={() => setPlaying(true)}
          className="group relative block w-full text-left"
          title={`Play: ${video.title}`}
        >
          <img
            src={video.thumbnail}
            alt={video.title}
            loading="lazy"
            className="w-full aspect-video object-cover"
          />
          <span className="absolute inset-0 flex items-center justify-center bg-black/30 group-hover:bg-black/20 transition-colors">
            <span className="w-12 h-12 rounded-full bg-accent flex items-center justify-center text-white shadow-lg group-hover:scale-105 transition-transform">
              <Play size={20} className="ml-0.5" fill="currentColor" />
            </span>
          </span>
        </button>
      )}
      <div className="px-3 py-2">
        <div className="flex items-start gap-1.5">
          <a
            href={video.url}
            target="_blank"
            rel="noreferrer"
            className="flex-1 text-xs font-semibold text-foreground hover:text-accent hover:underline line-clamp-2"
          >
            {video.title}
          </a>
          {video.verified && (
            <span
              title={`Captions match your topic (${Math.round((video.relevance ?? 0) * 100)}% overlap)`}
              className="flex items-center gap-1 shrink-0 text-[10px] font-semibold text-accent bg-accent/10 border border-accent/25 rounded-full px-1.5 py-0.5"
            >
              <BadgeCheck size={11} /> Verified
            </span>
          )}
        </div>
        {video.snippet && (
          <p className="text-[11px] text-muted-foreground line-clamp-2 mt-0.5">
            {video.snippet}
          </p>
        )}
      </div>
    </div>
  );
}

export default function InlineVideo({ message }: { message: ChatMessage }) {
  const args = (cardPayload(message)) as { videos?: VideoItem[] };
  const videos = Array.isArray(args.videos) ? args.videos : [];
  if (videos.length === 0) return null;
  return (
    <div className="space-y-2.5">
      {videos.map((v) => (
        <VideoCard key={v.video_id} video={v} />
      ))}
    </div>
  );
}

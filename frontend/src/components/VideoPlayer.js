import React, { useRef, useEffect } from "react";
import Hls from "hls.js";
import { Dialog, IconButton } from "@mui/material";
import CloseIcon from "@mui/icons-material/Close";

export default function VideoPlayer({ url, onClose }) {
  const videoRef = useRef();
  const hlsRef = useRef(null);

  useEffect(() => {
    const video = videoRef.current;

    // 清理上一個 Hls 實例
    if (hlsRef.current) {
      hlsRef.current.destroy();
      hlsRef.current = null;
    }

    // 只針對 m3u8 用 Hls.js
    if (url && url.endsWith(".m3u8") && Hls.isSupported()) {
      const hls = new Hls({debug: true});
      hls.loadSource(url);
      hls.attachMedia(video);
      hlsRef.current = hls;

      hls.on(Hls.Events.MANIFEST_PARSED, function() {
        console.log("HLS manifest loaded successfully");
        video.play();
      });

      hls.on(Hls.Events.ERROR, (event, data) => {
        console.error("HLS error:", data);
        if (data.fatal) {
          console.error("Fatal error:", data.type);
          hls.destroy();
        }
      });
    }
    // mp4/ts 只靠 React 控制 src 屬性即可

    // 清理
    return () => {
      if (hlsRef.current) {
        hlsRef.current.destroy();
        hlsRef.current = null;
      }
    };
  }, [url]);

  // 若是 m3u8 不設 src，其餘直接設
  const isHls = url && url.endsWith(".m3u8");
  const videoSrc = isHls ? undefined : url || "";

  return (
    <Dialog open={!!url} onClose={onClose} fullWidth maxWidth="md">
      <div style={{ position: "relative", background: "#000" }}>
        <video
          ref={videoRef}
          src={videoSrc}
          style={{ width: "100%", height: "100%" }}
          controls
          autoPlay
        >
          不支援此格式
        </video>
        <IconButton
          style={{ position: "absolute", top: 0, right: 0, color: "#fff" }}
          onClick={onClose}
        >
          <CloseIcon />
        </IconButton>
      </div>
    </Dialog>
  );
}

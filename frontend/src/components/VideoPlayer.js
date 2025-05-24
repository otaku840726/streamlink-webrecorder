import React, { useRef, useEffect } from "react";
import Hls from "hls.js";
import { Dialog, IconButton } from "@mui/material";
import CloseIcon from "@mui/icons-material/Close";

export default function VideoPlayer({ url, onClose }) {
  const videoRef = useRef();
  const hlsRef = useRef(null);

  useEffect(() => {
    const video = videoRef.current;
    // 清理前一次的 hls
    if (hlsRef.current) {
      hlsRef.current.destroy();
      hlsRef.current = null;
    }
    // 支援 m3u8 + Hls.js
    if (url && url.endsWith(".m3u8") && Hls.isSupported()) {
      const hls = new Hls();
      hls.loadSource(url);
      hls.attachMedia(video);
      hls.on(Hls.Events.ERROR, (event, data) => {
        if (data.fatal) hls.destroy();
      });
      hlsRef.current = hls;
    } else if (video && url) {
      video.src = url;
      video.load();
    }
    return () => {
      if (hlsRef.current) hlsRef.current.destroy();
    };
  }, [url]);

  return (
    <Dialog open={!!url} onClose={onClose} fullWidth maxWidth="md">
      <div style={{ position: "relative", background: "#000" }}>
        <video
          ref={videoRef}
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

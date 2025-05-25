import React, { useRef, useEffect, useState } from "react";
import Hls from "hls.js";
import { Dialog, IconButton } from "@mui/material";
import CloseIcon from "@mui/icons-material/Close";

// 修改這裡：添加 export default
const VideoPlayer = ({ url, onClose }) => {
  const videoRef = useRef();
  const hlsRef = useRef(null);
  
  // 清理時保持當前播放狀態
  const cleanup = () => {
    if (hlsRef.current) {
      hlsRef.current.destroy();
      hlsRef.current = null;
    }
  };

  useEffect(() => {
    return cleanup; // 組件卸載時清理
  }, []);

  useEffect(() => {
    if (!url) return;

    console.log('VideoPlayer - 開始載入 URL:', url);
    cleanup(); // 在設置新 URL 前清理

    if (!videoRef.current) {
      console.error('VideoPlayer - video element not ready');
      return;
    }

    if (url.endsWith('.m3u8')) {
      if (!Hls.isSupported()) {
        console.error('VideoPlayer - HLS not supported');
        return;
      }

      const hls = new Hls({
        debug: true,
        enableWorker: true,
        lowLatencyMode: true
      });

      hls.on(Hls.Events.MANIFEST_LOADING, () => {
        console.log('VideoPlayer - Manifest loading');
      });

      hls.on(Hls.Events.MANIFEST_LOADED, (event, data) => {
        console.log('VideoPlayer - Manifest loaded:', data);
      });

      hls.on(Hls.Events.ERROR, (event, data) => {
        console.error('HLS Error:', data);
        if (data.fatal) {
          switch (data.type) {
            case Hls.ErrorTypes.NETWORK_ERROR:
              hls.startLoad(); // 嘗試重新載入
              break;
            case Hls.ErrorTypes.MEDIA_ERROR:
              hls.recoverMediaError(); // 嘗試恢復媒體錯誤
              break;
            default:
              cleanup();
              break;
          }
        }
      });

      try {
        hls.loadSource(url);
        hls.attachMedia(videoRef.current);
        hlsRef.current = hls;
      } catch (error) {
        console.error('HLS initialization error:', error);
      }
    }
  }, [url]);

  return (
    <Dialog 
      open={!!url} 
      onClose={onClose}
      fullWidth 
      maxWidth="md"
    >
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

// 添加 export default
export default VideoPlayer;
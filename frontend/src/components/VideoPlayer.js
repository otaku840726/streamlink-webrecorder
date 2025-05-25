import React, { useRef, useEffect, useState } from "react";
import Hls from "hls.js";
import { Dialog, IconButton } from "@mui/material";
import CloseIcon from "@mui/icons-material/Close";

export default function VideoPlayer({ url, onClose }) {
  const videoRef = useRef();
  const hlsRef = useRef(null);
  const [isDialogOpen, setIsDialogOpen] = useState(false);

  // 清理函數
  const cleanup = () => {
    if (hlsRef.current) {
      hlsRef.current.destroy();
      hlsRef.current = null;
    }
  };

  // 處理視頻加載
  const initializePlayer = () => {
    if (!url) return;
    if (!videoRef.current) {
      console.error('VideoPlayer - video element not ready');
      return;
    }

    console.log('VideoPlayer - 開始載入 URL:', url);
    cleanup(); // 在設置新 URL 前清理

    if (url.endsWith('.m3u8')) {
      if (!Hls.isSupported()) {
        console.error('VideoPlayer - HLS not supported');
        return;
      }

      const hls = new Hls({
        debug: true,
        enableWorker: true,
        lowLatencyMode: true,
        manifestLoadingTimeOut: 20000, // 增加載入超時時間
        manifestLoadingMaxRetry: 3,    // 增加重試次數
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
              console.log('嘗試重新載入...');
              hls.startLoad(); // 嘗試重新載入
              break;
            case Hls.ErrorTypes.MEDIA_ERROR:
              console.log('嘗試恢復媒體錯誤...');
              hls.recoverMediaError(); // 嘗試恢復媒體錯誤
              break;
            default:
              console.log('致命錯誤，清理資源...');
              cleanup();
              break;
          }
        }
      });

      try {
        hls.loadSource(url);
        hls.attachMedia(videoRef.current);
        hlsRef.current = hls;

        // 添加視頻事件監聽
        videoRef.current.addEventListener('loadedmetadata', () => {
          console.log('Video metadata loaded');
        });

        videoRef.current.addEventListener('error', (e) => {
          console.error('Video error:', e);
        });
      } catch (error) {
        console.error('HLS initialization error:', error);
      }
    }
  };

  // 處理 Dialog 開關
  useEffect(() => {
    if (url) {
      setIsDialogOpen(true);
    }
  }, [url]);

  // 當 Dialog 完全打開後再初始化播放器
  useEffect(() => {
    if (isDialogOpen && videoRef.current) {
      console.log('Dialog is open, initializing player...');
      initializePlayer();
    }
  }, [isDialogOpen, url]);

  // 組件卸載時清理
  useEffect(() => {
    return cleanup;
  }, []);

  const handleClose = () => {
    setIsDialogOpen(false);
    cleanup();
    if (onClose) onClose();
  };

  return (
    <Dialog 
      open={isDialogOpen} 
      onClose={handleClose}
      fullWidth 
      maxWidth="md"
      TransitionProps={{
        onEntered: () => {
          console.log('Dialog transition completed');
          initializePlayer(); // Dialog 完全打開後再次嘗試初始化
        }
      }}
    >
      <div style={{ 
        position: "relative", 
        background: "#000",
        width: "100%",
        height: "calc(100vh - 64px)", // 調整高度
        maxHeight: "calc(100vh - 64px)",
      }}>
        <video
          ref={videoRef}
          style={{ 
            width: "100%", 
            height: "100%",
            objectFit: "contain" 
          }}
          controls
          autoPlay
          playsInline // 加入 playsInline 屬性
        >
          不支援此格式
        </video>
        <IconButton
          style={{ 
            position: "absolute", 
            top: 8, 
            right: 8, 
            color: "#fff",
            backgroundColor: "rgba(0,0,0,0.5)" 
          }}
          onClick={handleClose}
        >
          <CloseIcon />
        </IconButton>
      </div>
    </Dialog>
  );
}
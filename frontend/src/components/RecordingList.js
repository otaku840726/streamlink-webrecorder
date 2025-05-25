import React, { useEffect, useState } from 'react';
import { Box, Typography, Card, CardContent, Button, CardMedia, Grid } from '@mui/material';
import api from '../api';

// 缩略图轮播组件
function ThumbnailCarousel({ taskId, filename }) {
  const [thumbs, setThumbs] = useState([]);
  const [index, setIndex] = useState(0);

  useEffect(() => {
    api.listThumbnails(taskId, filename)
        .then((urls) => setThumbs(urls))
        .catch(() => setThumbs([]));
  }, [taskId, filename]);

  useEffect(() => {
    if (thumbs.length > 1) {
      const timer = setInterval(() => {
        setIndex((i) => (i + 1) % thumbs.length);
      }, 1000);
      return () => clearInterval(timer);
    }
  }, [thumbs]);

  const src = thumbs.length > 0 ? thumbs[index] : '';
  return (
      <CardMedia
          component="img"
          height="140"
          image={src}
          alt={filename}
          sx={{ backgroundColor: '#eee' }}
      />
  );
}

export default function RecordingList({ task, onPlay }) {
  const [recordings, setRecordings] = useState([]);
  const [isActive, setIsActive] = useState(false);

  const reload = async () => {
    try {
      const recs = await api.listRecordings(task.id);
      setRecordings(recs);
      const active = await api.getActiveRecordings();
      setIsActive(active.includes(task.id));
    } catch {
      setRecordings([]);
      setIsActive(false);
    }
  };

  useEffect(() => {
    reload();
    const t = setInterval(reload, 5000);
    return () => clearInterval(t);
  }, [task.id]);

  return (
      <Box sx={{ my: 4, px: 2 }}>
        <Typography variant="h5" align="center" gutterBottom>
          錄影清單 - {task.name} {isActive && <Box component="span" color="error.main">● 錄影中</Box>}
        </Typography>

        <Box sx={{ display: 'flex', justifyContent: 'center', mb: 2 }}>
          {isActive ? (
              <Button
                  variant="contained"
                  color="error"
                  onClick={async () => {
                    if (window.confirm('確定要停止錄影？')) {
                      await api.stopRecording(task.id);
                      setTimeout(reload, 1000);
                    }
                  }}
              >停止錄影</Button>
          ) : (
              <Button
                  variant="contained"
                  color="primary"
                  onClick={async () => {
                    if (window.confirm('確定要重新開始錄影？')) {
                      await api.updateTask({ ...task });
                      setTimeout(reload, 1000);
                    }
                  }}
              >再錄製</Button>
          )}
          {task.hls_enable && (
              <Button
                  variant="outlined"
                  color="secondary"
                  sx={{ ml: 2 }}
                  onClick={() => onPlay(`/hls/${task.id}/stream.m3u8`)}
              >直播觀看</Button>
          )}
        </Box>

        <Grid container spacing={3} justifyContent="center">
          {recordings.map((rec) => (
              <Grid item key={rec.file} xs={12} sm={6} md={4} lg={3}>
                <Card sx={{ height: '100%', display: 'flex', flexDirection: 'column', bgcolor: 'grey.50', boxShadow: 3, borderRadius: 2 }}>
                  <ThumbnailCarousel taskId={task.id} filename={rec.file} />
                  <CardContent sx={{ flexGrow: 1 }}>
                    <Typography variant="subtitle1" noWrap>{rec.file}</Typography>
                    <Typography variant="body2" color="text.secondary">大小: {(rec.size / 1024 / 1024).toFixed(1)} MB</Typography>
                    <Typography variant="body2" color="text.secondary">錄影時間: {new Date(rec.mtime).toLocaleString()}</Typography>
                  </CardContent>
                  <Box sx={{ p: 1, pt: 0, display: 'flex', justifyContent: 'space-between', bgcolor: 'grey.100' }}>
                    <Button
                        size="small"
                        variant="outlined"
                        onClick={() => {
                          const baseUrl = `/tasks/${task.id}/recordings/${rec.file}`;
                          const playUrl = rec.file.toLowerCase().endsWith('.ts') ? `${baseUrl}/mp4` : baseUrl;
                          onPlay(playUrl);
                        }}
                    >播放</Button>
                    <Button
                        size="small"
                        variant="outlined"
                        color="error"
                        onClick={async () => {
                          if (window.confirm('確定要刪除這個錄影檔？')) {
                            await api.deleteRecording(task.id, rec.file);
                            reload();
                          }
                        }}
                    >刪除</Button>
                  </Box>
                </Card>
              </Grid>
          ))}
        </Grid>
      </Box>
  );
}

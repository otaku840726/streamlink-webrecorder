import React, { useEffect, useState } from 'react';
import {
  Box, Typography, Card, CardContent, Button, CardMedia,
  Grid, Dialog, DialogTitle, DialogContent, DialogActions,
  FormControl, InputLabel, Select, MenuItem, LinearProgress
} from '@mui/material';
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
  const [convertDialog, setConvertDialog] = useState(false);
  const [selectedFile, setSelectedFile] = useState(null);
  const [quality, setQuality] = useState('high');
  const [conversionStatus, setConversionStatus] = useState({});


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

  // —— 新增：组件挂载时，初始化拉一次所有转码状态 —— 
  useEffect(() => {
    api.getConversionStatus()
      .then(statuses => setConversionStatus(statuses))
      .catch(err => console.error('初始化转码状态失败', err));
  }, []);

  // —— 调整：每 3s 全量拉取 conversion_tasks —— 
  useEffect(() => {
    const id = setInterval(async () => {
      try {
        const statuses = await api.getConversionStatus();
        setConversionStatus(statuses);
      } catch (err) {
        console.error('获取转码状态失败', err);
      }
    }, 3000);
    return () => clearInterval(id);
  }, []);

  const handleConvertClick = (rec) => {
    setSelectedFile(rec);
    setConvertDialog(true);
  };

  const startConversion = async () => {
    if (!selectedFile) return;
    try {
      const result = await api.convertRecording(task.id, selectedFile.file, quality);
      // 直接用后端回来的 task_key
      const key = result.task_key;
      setConversionStatus(prev => ({
        ...prev,
        [key]: { status: 'processing', progress: 0 }
      }));
      setConvertDialog(false);
    } catch (error) {
      console.error('转码请求失败', error);
    }
  };

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
        {recordings.map((rec) => {
          const isTs = rec.file.toLowerCase().endsWith('.ts');
          const taskKey = `${task.id}_${rec.file}`;
          const converting = conversionStatus[taskKey];

          return (
            <Grid item key={rec.file} xs={12} sm={recordings.length > 1 ? 6 : 12} md={recordings.length > 1 ? 4 : 8} lg={recordings.length > 1 ? 3 : 6}>
              <Card sx={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
                <ThumbnailCarousel taskId={task.id} filename={rec.file} />
                <CardContent sx={{ flexGrow: 1 }}>
                  <Typography variant="subtitle1" noWrap>{rec.file}</Typography>
                  <Typography variant="body2" color="text.secondary">大小: {(rec.size / 1024 / 1024).toFixed(1)} MB</Typography>
                  <Typography variant="body2" color="text.secondary">錄影時間: {new Date(rec.mtime).toLocaleString()}</Typography>

                  {/* 显示转码状态 */}
                  {converting && (
                    <Box sx={{ mt: 1 }}>
                      {converting.status === 'processing' && (
                        <>
                          <Typography variant="body2" color="primary">
                            轉碼中... {`${Math.round(converting.progress || 0)}%`}
                          </Typography>
                          <LinearProgress
                            variant="determinate"
                            value={converting.progress || 0}
                            sx={{ mt: 0.5 }}
                          />
                        </>
                      )}
                      {converting.status === 'completed' && (
                        <Typography variant="body2" color="success.main">
                          轉碼完成: {converting.original_size?.toFixed(1)} MB → {converting.new_size?.toFixed(1)} MB
                        </Typography>
                      )}
                      {converting.status === 'failed' && (
                        <Typography variant="body2" color="error">轉碼失敗</Typography>
                      )}
                    </Box>
                  )}
                </CardContent>
                {/* 底部按钮区（播放/转码/删除） */}
                <Box sx={{ p: 1, pt: 0, display: 'flex', justifyContent: 'space-between', marginTop: 'auto' }}>
                  <Button
                    size="small" variant="outlined"
                    onClick={() => {
                      const baseUrl = `/tasks/${task.id}/recordings/${rec.file}`;
                      onPlay(isTs ? `${baseUrl}/mp4` : baseUrl);
                    }}
                  >播放</Button>

                  {isTs && converting?.status !== 'processing' && (
                    <Button
                      size="small" variant="outlined" color="primary"
                      onClick={() => handleConvertClick(rec)}
                    >轉碼</Button>
                  )}

                  <Button
                    size="small" variant="outlined" color="error"
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
          );
        })}
      </Grid>

      {/* 转码选项对话框 */}
      <Dialog open={convertDialog} onClose={() => setConvertDialog(false)}>
        <DialogTitle>選擇轉碼品質</DialogTitle>
        <DialogContent>
          <FormControl fullWidth sx={{ mt: 2 }}>
            <InputLabel>壓縮品質</InputLabel>
            <Select
              value={quality}
              label="壓縮品質"
              onChange={(e) => setQuality(e.target.value)}
            >
              <MenuItem value="extreme">極高壓縮 (最小檔案)</MenuItem>
              <MenuItem value="high">高壓縮 (推薦)</MenuItem>
              <MenuItem value="medium">中等壓縮</MenuItem>
              <MenuItem value="low">低壓縮 (最高畫質)</MenuItem>
            </Select>
          </FormControl>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setConvertDialog(false)}>取消</Button>
          <Button onClick={startConversion} variant="contained">開始轉碼</Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
}

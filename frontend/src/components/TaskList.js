import React, { useEffect, useState } from 'react';
import { Box, Grid, Card, CardContent, Typography, Button } from '@mui/material';
import api from '../api';

export default function TaskList({ tasks, onSelectTask, onEditTask, onShowLogs, reload }) {
  useEffect(() => {
    // 如果需要自动刷新，可在这里设置定时器
  }, []);

  return (
      <Box sx={{ p: 2, overflowX: 'hidden' }}>
        <Grid container spacing={2} justifyContent="flex-start">
          {tasks.map((t) => (
              <Grid item key={t.id} xs={12} sm={6} md={4} lg={3}>
                <Card sx={{ height: '100%', display: 'flex', flexDirection: 'column', boxShadow: 2, borderRadius: 2 }}>
                  <CardContent sx={{ flexGrow: 1 }}>
                    <Typography variant="h6" noWrap gutterBottom>
                      {t.name}
                    </Typography>
                    <Typography variant="body2" noWrap gutterBottom>
                      URL: {t.url}
                    </Typography>
                    <Typography variant="body2" gutterBottom>
                      間隔：{t.interval} 分鐘
                    </Typography>
                    <Typography variant="body2" noWrap>
                      路徑：{t.save_dir}
                    </Typography>
                  </CardContent>
                  <Box sx={{ p: 1, pt: 0, display: 'flex', flexWrap: 'wrap', gap: 1, bgcolor: 'grey.100' }}>
                    <Button size="small" variant="contained" onClick={() => onSelectTask(t)}>
                      錄影
                    </Button>
                    <Button size="small" variant="outlined" onClick={() => onShowLogs(t)}>
                      紀錄
                    </Button>
                    <Button size="small" variant="outlined" onClick={() => onEditTask(t)}>
                      編輯
                    </Button>
                    <Button
                        size="small"
                        variant="outlined"
                        color="error"
                        onClick={async () => {
                          if (window.confirm('確定要刪除這個任務？')) {
                            await api.deleteTask(t.id);
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

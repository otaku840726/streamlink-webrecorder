// src/components/TaskList.js
import React, { useEffect, useState } from 'react';
import {
    Box,
    Grid,
    Card,
    CardContent,
    Typography,
    Button,
    Chip
} from '@mui/material';
import api from '../api';

export default function TaskList({ tasks, reload, onSelectTask, onShowLogs, onEditTask }) {
    const [activeTasks, setActiveTasks] = useState([]);
    const [lastTimes, setLastTimes] = useState({});
    const [recordCounts, setRecordCounts] = useState({});

    // 获取录制状态、最新时间和录制数量
    useEffect(() => {
        const fetchStatus = async () => {
            try {
                const active = await api.getActiveRecordings();
                setActiveTasks(active);

                const times = {};
                const counts = {};

                await Promise.all(tasks.map(async (t) => {
                    const recs = await api.listRecordings(t.id);
                    if (recs.length > 0) {
                        times[t.id] = recs[0].mtime;
                    }
                    counts[t.id] = recs.length;
                }));

                setLastTimes(times);
                setRecordCounts(counts);
            } catch (e) {
                console.error('获取录制状态或时间失败', e);
            }
        };
        if (tasks.length) fetchStatus();
    }, [tasks]);

    return (
        <Box sx={{ p: 2, overflowX: 'hidden' }}>
            <Grid container spacing={2} justifyContent="flex-start">
                {tasks.map((t) => (
                    <Grid item key={t.id} xs={12} sm={6} md={4} lg={3}>
                        <Card sx={{ height: '100%', display: 'flex', flexDirection: 'column', boxShadow: 2, borderRadius: 2 }}>
                            <CardContent sx={{ flexGrow: 1 }}>
                                <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                                    <Typography variant="h6" noWrap>
                                        {t.name}
                                    </Typography>
                                    {activeTasks.includes(t.id) ? (
                                        <Chip label="錄影中" color="error" size="small" />
                                    ) : (
                                        <Chip label="空閒" size="small" />
                                    )}
                                </Box>
                                <Typography variant="body2" noWrap gutterBottom>
                                    URL: {t.url}
                                </Typography>
                                <Typography variant="body2" gutterBottom>
                                    間隔：{t.interval} 分鐘
                                </Typography>
                                <Typography variant="body2" noWrap gutterBottom>
                                    路徑：{t.save_dir}
                                </Typography>
                                {recordCounts[t.id] != null && (
                                    <Typography variant="body2" color="text.secondary">
                                        已錄製：{recordCounts[t.id]} 次
                                    </Typography>
                                )}
                                {lastTimes[t.id] && (
                                    <Typography variant="caption" color="text.secondary">
                                        最新錄製：{new Date(lastTimes[t.id]).toLocaleString()}
                                    </Typography>
                                )}
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
                            </Box>
                        </Card>
                    </Grid>
                ))}
            </Grid>
        </Box>
    );
}

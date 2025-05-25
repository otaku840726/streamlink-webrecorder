// src/App.js
import React, { useState, useEffect } from "react";
import {
  Box,
  Dialog,
  AppBar,
  Toolbar,
  IconButton,
  Typography,
  useTheme,
  useMediaQuery,
} from "@mui/material";
import CloseIcon from "@mui/icons-material/Close";

import api from "./api";
import TaskList from "./components/TaskList";
import TaskForm from "./components/TaskForm";
import RecordingList from "./components/RecordingList";
import LogList from "./components/LogList";
import VideoPlayer from "./components/VideoPlayer";

export default function App() {
  const [view, setView] = useState(null);
  // view: null | { type: 'recordings'|'logs'|'new', task: Task }
  const [tasks, setTasks] = useState([]);
  const [playUrl, setPlayUrl] = useState(null);

  const theme = useTheme();
  const isMobile = useMediaQuery(theme.breakpoints.down("sm"));

  // 拉取并更新任务列表
  const reloadTasks = async () => {
    try {
      const data = await api.listTasks();
      setTasks(data);
    } catch (err) {
      console.error("加载任务失败", err);
    }
  };

  useEffect(() => {
    reloadTasks();
  }, []);

  // 打开各视图
  const openRecordings = (task) => setView({ type: "recordings", task });
  const openLogs       = (task) => setView({ type: "logs",        task });
  const openForm       = (task) => setView({ type: "new",         task });

  // 关闭“新建/编辑”并刷新列表
  const closeForm = () => {
    setView(null);
    reloadTasks();
  };
  // 关闭其他弹窗
  const closeDialog = () => setView(null);

  // 播放回调
  const handlePlay = (url) => {
    // 如果是相对路径，前面加上 BASE API
    const fullUrl = `${process.env.REACT_APP_API || ""}${url}`;
    setPlayUrl(fullUrl);
  };

  return (
      <Box sx={{ height: "100vh", display: "flex", flexDirection: "column" }}>
        {/* —— 应用标题栏 —— */}
        <AppBar position="static">
          <Toolbar>
            <Typography variant="h6" component="div">
              Streamlink Recorder
            </Typography>
            <Button color="inherit" onClick={() => openForm(null)}>
              新增任務
            </Button>
          </Toolbar>
        </AppBar>

        {/* —— 主列表区（永远挂载，不会卸载） —— */}
        <Box sx={{ flex: 1, overflow: "auto" }}>
          <TaskList
              tasks={tasks}
              reload={reloadTasks}
              onSelectTask={openRecordings}
              onShowLogs={openLogs}
              onEditTask={openForm}
          />
        </Box>

        {/* —— 录影列表对话框 —— */}
        <Dialog
            open={view?.type === "recordings"}
            fullScreen={isMobile}
            onClose={closeDialog}
            maxWidth="lg"
        >
          <AppBar position="static">
            <Toolbar>
              <IconButton edge="start" color="inherit" onClick={closeDialog}>
                <CloseIcon />
              </IconButton>
              <Typography variant="h6" sx={{ ml: 2 }}>
                錄影清單 – {view?.task?.name}
              </Typography>
            </Toolbar>
          </AppBar>
          {view?.task && (
              <RecordingList task={view.task} onPlay={handlePlay} />
          )}
        </Dialog>

        {/* —— 日志列表对话框 —— */}
        <Dialog
            open={view?.type === "logs"}
            fullScreen={isMobile}
            onClose={closeDialog}
            maxWidth="lg"
        >
          <AppBar position="static">
            <Toolbar>
              <IconButton edge="start" color="inherit" onClick={closeDialog}>
                <CloseIcon />
              </IconButton>
              <Typography variant="h6" sx={{ ml: 2 }}>
                日誌 – {view?.task?.name}
              </Typography>
            </Toolbar>
          </AppBar>
          {view?.task && <LogList task={view.task} />}
        </Dialog>

        {/* —— 新增/编辑任务对话框 —— */}
        <Dialog
            open={view?.type === "new"}
            fullScreen={isMobile}
            onClose={closeForm}
        >
          <TaskForm
              open={true}
              task={view?.task}
              onClose={closeForm}
          />
        </Dialog>

        {/* —— 视频播放器 —— */}
        {playUrl && (
            <VideoPlayer url={playUrl} onClose={() => setPlayUrl(null)} />
        )}
      </Box>
  );
}

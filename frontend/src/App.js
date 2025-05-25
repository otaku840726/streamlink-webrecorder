import React, { useState, useEffect } from "react";
import RecordingList from "./components/RecordingList";
import VideoPlayer from "./components/VideoPlayer";
import TaskList from "./components/TaskList";
import TaskForm from "./components/TaskForm";
import LogList from "./components/LogList";
import api from "./api";
import { Container, Typography, Box, Button, Collapse } from "@mui/material";

export default function App() {
  const [playUrl, setPlayUrl] = useState(null);
  const [tasks, setTasks] = useState([]);
  const [selectedTask, setSelectedTask] = useState(null);
  const [tab, setTab] = useState("tasks");
  const [openForm, setOpenForm] = useState(false);
  const [scrollPos, setScrollPos] = useState(0);

  // 加载任务列表并定时刷新
  const reloadTasks = async () => {
    setTasks(await api.listTasks());
  };

  useEffect(() => {
    reloadTasks();
    const timer = setInterval(reloadTasks, 5000);
    return () => clearInterval(timer);
  }, []);

  // 当切换回任务列表时，恢复之前的滚动位置
  useEffect(() => {
    if (tab === 'tasks') {
      window.scrollTo(0, scrollPos);
    }
  }, [tab, scrollPos]);

  const handleFormClose = () => {
    setOpenForm(false);
    setSelectedTask(null);
    reloadTasks();
  };

  const handlePlay = (url) => {
    setPlayUrl(url);
  };

  // 返回任务列表
  const handleBack = () => {
    setTab("tasks");
    setSelectedTask(null);
    setPlayUrl(null);
  };

  return (
      <Container>
        <Box sx={{ py: 3 }}>
          <Typography variant="h4" gutterBottom>
            Streamlink Web Recorder Manager
          </Typography>

          {/* 新增任务按钮，仅在任务列表页显示 */}
          {tab === "tasks" && (
              <Button
                  variant="contained"
                  sx={{ mb: 2 }}
                  onClick={() => {
                    setSelectedTask(null);
                    setOpenForm(true);
                  }}
              >
                新增任務
              </Button>
          )}

          {/* 任务列表，可折叠 */}
          <Collapse in={tab === "tasks"} unmountOnExit>
            <TaskList
                tasks={tasks}
                onSelectTask={(task) => {
                  // 进入子页前记录滚动位置
                  setScrollPos(window.pageYOffset);
                  setSelectedTask(task);
                  setTab("recordings");
                }}
                onEditTask={(task) => {
                  setSelectedTask(task);
                  setOpenForm(true);
                }}
                onShowLogs={(task) => {
                  // 进入日志页前记录滚动位置
                  setScrollPos(window.pageYOffset);
                  setSelectedTask(task);
                  setTab("logs");
                }}
                reload={reloadTasks}
            />
          </Collapse>

          {/* 返回按钮，仅在子页显示 */}
          {tab !== "tasks" && (
              <Button variant="text" onClick={handleBack} sx={{ mb: 2 }}>
                ← 返回任務列表
              </Button>
          )}

          {/* 任务表单弹窗 */}
          <TaskForm open={openForm} task={selectedTask} onClose={handleFormClose} />
        </Box>

        {/* 视频播放器弹窗 */}
        <VideoPlayer url={playUrl} onClose={() => setPlayUrl(null)} />

        {/* 子页：录影列表或日志列表 */}
        {selectedTask && tab === "recordings" && (
            <RecordingList task={selectedTask} onPlay={handlePlay} />
        )}
        {selectedTask && tab === "logs" && <LogList task={selectedTask} />}
      </Container>
  );
}

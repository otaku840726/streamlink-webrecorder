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

  const reloadTasks = async () => {
    setTasks(await api.listTasks());
  };

  useEffect(() => {
    reloadTasks();
    const timer = setInterval(() => reloadTasks(), 5000);
    return () => clearInterval(timer);
  }, []);

  const handleFormClose = () => {
    setOpenForm(false);
    setSelectedTask(null);
    reloadTasks();
  };

  const handlePlay = (url) => {
    setPlayUrl(url);
  };

  const handleBack = () => {
    // 恢复滚动位置
    const currentScroll = window.pageYOffset || document.documentElement.scrollTop;
    setScrollPos(currentScroll);
    setTab("tasks");
    setSelectedTask(null);
    setPlayUrl(null);
  };

  return (
      <div>
        <Container>
          <Box sx={{ py: 3 }}>
            <Typography variant="h4" gutterBottom>
              Streamlink Web Recorder Manager
            </Typography>

            {/* 新增按鈕僅在任務列表顯示 */}
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

            {/* 任務列表 Collapse */}
            <Collapse in={tab === "tasks"} unmountOnExit>
              <TaskList
                  tasks={tasks}
                  onSelectTask={(task) => {
                    setSelectedTask(task);
                    setTab("recordings");
                  }}
                  onEditTask={(task) => {
                    setSelectedTask(task);
                    setOpenForm(true);
                  }}
                  onShowLogs={(task) => {
                    setSelectedTask(task);
                    setTab("logs");
                  }}
                  reload={reloadTasks}
              />
            </Collapse>

            {/* 返回按鈕 */}
            {tab !== "tasks" && (
                <Button variant="text" onClick={handleBack} sx={{ mb: 2 }}>
                  ← 返回任務列表
                </Button>
            )}

            {/* 任務表單 */}
            <TaskForm open={openForm} task={selectedTask} onClose={handleFormClose} />
          </Box>
        </Container>

        {/* 播放器 */}
        <VideoPlayer url={playUrl} onClose={() => setPlayUrl(null)} />

        {/* 子頁面：錄影清單或紀錄 */}
        {selectedTask && tab === "recordings" && (
            <RecordingList task={selectedTask} onPlay={handlePlay} />
        )}
        {selectedTask && tab === "logs" && <LogList task={selectedTask} />}
      </div>
  );
}

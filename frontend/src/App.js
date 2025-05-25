import React, { useState, useEffect } from "react";
import { Container, Typography, Box, Button } from "@mui/material";
import TaskList from "./components/TaskList";
import TaskForm from "./components/TaskForm";
import RecordingList from "./components/RecordingList";
import VideoPlayer from "./components/VideoPlayer";
import { getVideoPlayerProps } from "./components/RecordingList";
import LogList from "./components/LogList";
import api from "./api";

export default function App() {
  const [tasks, setTasks] = useState([]);
  const [selectedTask, setSelectedTask] = useState(null);
  const [tab, setTab] = useState("tasks");
  const [openForm, setOpenForm] = useState(false);

  const reloadTasks = async () => {
    setTasks(await api.listTasks());
  };

  useEffect(() => {
    reloadTasks();
    // 定時刷新
    const timer = setInterval(() => reloadTasks(), 5000);
    return () => clearInterval(timer);
  }, []);

  // 彈窗關閉後務必清空 selectedTask，防止下次開啟內容殘留
  const handleFormClose = () => {
    setOpenForm(false);
    setSelectedTask(null);
    reloadTasks();
  };

  // 獲取 VideoPlayer 的 props
  const videoPlayerProps = getVideoPlayerProps();

  return (
    <Container>
      <Box sx={{ py: 3 }}>
        <Typography variant="h4" gutterBottom>
          Streamlink Web Recorder Manager
        </Typography>
        <Button
          variant="contained"
          onClick={() => {
            setSelectedTask(null);  // 新增時 task = null
            setOpenForm(true);
          }}
          sx={{ mb: 2 }}
        >
          新增任務
        </Button>
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
        <TaskForm
          open={openForm}
          task={selectedTask}
          onClose={handleFormClose}
        />
        {selectedTask && tab === "recordings" && (
          <RecordingList task={selectedTask} />
        )}
        {selectedTask && tab === "logs" && <LogList task={selectedTask} />}
        {/* VideoPlayer 移到這裡，不受列表更新影響 */}
        {videoPlayerProps.url && (
          <VideoPlayer
            url={videoPlayerProps.url}
            onClose={videoPlayerProps.onClose}
          />
        )}
      </Box>
    </Container>
  );
}

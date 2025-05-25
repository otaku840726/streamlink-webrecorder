import React, { useState } from "react";
import RecordingList from "./components/RecordingList";
import VideoPlayer from "./components/VideoPlayer";
// ... 其他 imports
import { Container, Typography, Box, Button } from "@mui/material";
import TaskList from "./components/TaskList";
import TaskForm from "./components/TaskForm";
import LogList from "./components/LogList";
import api from "./api";
import { useEffect } from "react";

export default function App() {
  // ... 其他狀態
  const [playUrl, setPlayUrl] = useState(null);
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

  // 提供給子組件的播放處理函數
  const handlePlay = (url) => {
    setPlayUrl(url);
  };

  return (
    <div>
      {/* ... 其他 UI 元素 */}
      <Container>
        <Box sx={{ py: 3 }}>
          <Typography variant="h4" gutterBottom>
            Streamlink Web Recorder Manager
          </Typography>
          <Button
            variant="contained"
            onClick={() => {
              setSelectedTask(null); // 新增時 task = null
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
          {/* ... 其他組件 */}
        </Box>
      </Container>

      {/* VideoPlayer 移到最外層 */}
      <VideoPlayer 
        url={playUrl} 
        onClose={() => setPlayUrl(null)}
      />

      {selectedTask && tab === "recordings" && (
        <RecordingList 
          task={selectedTask} 
          onPlay={handlePlay}  // 傳入播放處理函數
        />
      )}
      {selectedTask && tab === "logs" && <LogList task={selectedTask} />}
    </div>
  );
}
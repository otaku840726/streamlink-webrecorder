import React, { useState } from "react";
import {
  Box,
  IconButton,
  Drawer,
  AppBar,
  Toolbar,
  Typography,
  useTheme,
  useMediaQuery
} from "@mui/material";
import MenuIcon from "@mui/icons-material/Menu";
import TaskList from "./TaskList";
import RecordingList from "./RecordingList";
import LogList from "./LogList";
import TaskForm from "./TaskForm";
import VideoPlayer from "./VideoPlayer";

export default function App() {
  const [tab, setTab] = useState("tasks");
  const [currentTask, setCurrentTask] = useState(null);
  const [drawerOpen, setDrawerOpen] = useState(false);

  const theme = useTheme();
  const isMobile = useMediaQuery(theme.breakpoints.down("sm"));

  // 切到子页时自动关抽屉；回任务页可留着不动
  const handleSelectTask = (task) => {
    setCurrentTask(task);
    setTab("recordings");
    if (isMobile) setDrawerOpen(false);
  };

  // AppBar 上的菜单键
  const renderMenuButton = () => (
      isMobile && (
          <IconButton
              color="inherit"
              edge="start"
              onClick={() => setDrawerOpen(true)}
              sx={{ mr: 2 }}
          >
            <MenuIcon />
          </IconButton>
      )
  );

  return (
      <Box sx={{ display: "flex", height: "100vh", overflow: "hidden" }}>
        {/* 左侧抽屉：任务列表 */}
        <Drawer
            variant="temporary"
            open={drawerOpen}
            onClose={() => setDrawerOpen(false)}
            ModalProps={{ keepMounted: true }}  // <-- 最关键：隐藏时保留 DOM
            sx={{
              "& .MuiDrawer-paper": {
                width: 300,
                boxSizing: "border-box",
              },
            }}
        >
          <TaskList
              onSelect={handleSelectTask}
              onShowLogs={() => { setTab("logs"); if (isMobile) setDrawerOpen(false); }}
              onNewTask={() => setTab("new")}
          />
        </Drawer>

        {/* 主内容区 */}
        <Box sx={{ flex: 1, display: "flex", flexDirection: "column", overflow: "auto" }}>
          {/* 顶部 AppBar */}
          <AppBar position="static">
            <Toolbar>
              {renderMenuButton()}
              <Typography variant="h6" component="div" sx={{ flexGrow: 1 }}>
                {tab === "tasks" && "任務列表"}
                {tab === "recordings" && `錄影清單 - ${currentTask?.name}`}
                {tab === "logs" && `日誌 - ${currentTask?.name}`}
                {tab === "new" && "新增任務"}
              </Typography>
              {tab !== "tasks" && (
                  <Button color="inherit" onClick={() => { setTab("tasks"); }}>
                    返回任務列表
                  </Button>
              )}
            </Toolbar>
          </AppBar>

          {/* 根据 tab 渲染 */}
          {tab === "tasks" && (
              // 在桌面端也始终渲染：让 Drawer keepMounted=true 后可切换
              <Box sx={{ p: 2 }}>
                <TaskList
                    onSelect={handleSelectTask}
                    onShowLogs={() => setTab("logs")}
                    onNewTask={() => setTab("new")}
                />
              </Box>
          )}
          {tab === "recordings" && currentTask && (
              <RecordingList task={currentTask} onPlay={(url) => setPlayerUrl(url)} />
          )}
          {tab === "logs" && currentTask && (
              <LogList task={currentTask} />
          )}
          {tab === "new" && (
              <TaskForm onSaved={() => setTab("tasks")} />
          )}
          {playerUrl && (
              <VideoPlayer url={playerUrl} onClose={() => setPlayerUrl(null)} />
          )}
        </Box>
      </Box>
  );
}

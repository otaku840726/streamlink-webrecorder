import React, { useEffect, useState } from "react";
import {
  Box,
  Typography,
  Table,
  TableHead,
  TableBody,
  TableRow,
  TableCell,
  Paper,
  IconButton,
  Tooltip,
  TableContainer,
  Card,
  CardContent,
  Stack,
  useMediaQuery,
  useTheme,
  createTheme,
  ThemeProvider
} from "@mui/material";
import PlayArrowIcon from '@mui/icons-material/PlayArrow';
import DownloadIcon from '@mui/icons-material/Download';

const theme = createTheme({
  palette: {
    primary: { main: '#1976d2' },
    background: { default: '#f5f7fa', paper: '#ffffff' }
  },
  typography: {
    h5: { fontWeight: 600, letterSpacing: '0.5px' },
    body1: { fontSize: '0.95rem' }
  },
  shape: {
    borderRadius: 12
  }
});

export default function RecordingList({ task }) {
  const [recordings, setRecordings] = useState([]);
  const [playUrl, setPlayUrl] = useState(null);
  const muiTheme = useTheme();
  const isMobile = useMediaQuery(muiTheme.breakpoints.down('sm'));

  useEffect(() => {
    loadRecordings();
  }, [task]);

  const loadRecordings = async () => {
    const list = await api.listRecordings(task.id);
    setRecordings(list);
  };

  const handlePlay = (file) => {
    setPlayUrl(`/tasks/${task.id}/recordings/${file}/mp4`);
  };

  const renderCardItem = (rec) => (
      <Card key={rec.file} sx={{ mb: 2, borderRadius: 2, boxShadow: 1 }}>
        <CardContent>
          <Stack spacing={1}>
            <Typography variant="body1" sx={{ fontWeight: 500 }}>{rec.file}</Typography>
            <Typography variant="body2">大小: {rec.size}</Typography>
            <Typography variant="body2">時間: {new Date(rec.timestamp).toLocaleString()}</Typography>
            <Stack direction="row" spacing={1} justifyContent="flex-end">
              <Tooltip title="Play">
                <IconButton onClick={() => handlePlay(rec.file)} color="primary">
                  <PlayArrowIcon />
                </IconButton>
              </Tooltip>
              <Tooltip title="Download">
                <IconButton component="a" href={`/tasks/${task.id}/recordings/${rec.file}/mp4?download=true`} color="primary">
                  <DownloadIcon />
                </IconButton>
              </Tooltip>
            </Stack>
          </Stack>
        </CardContent>
      </Card>
  );

  return (
      <ThemeProvider theme={theme}>
        <Box sx={{ p: isMobile ? 2 : 4, bgcolor: 'background.default', minHeight: '100vh' }}>
          <Paper sx={{ p: isMobile ? 2 : 3, mb: isMobile ? 2 : 4, elevation: 3 }}>
            <Typography variant="h5" gutterBottom>
              錄影列表
            </Typography>
            {isMobile ? (
                recordings.map(renderCardItem)
            ) : (
                <TableContainer component={Paper} elevation={1} sx={{ borderRadius: 2 }}>
                  <Table>
                    <TableHead>
                      <TableRow>
                        <TableCell>檔案名稱</TableCell>
                        <TableCell align="right">大小</TableCell>
                        <TableCell align="right">時間戳</TableCell>
                        <TableCell align="center">動作</TableCell>
                      </TableRow>
                    </TableHead>
                    <TableBody>
                      {recordings.map((rec) => (
                          <TableRow key={rec.file} hover>
                            <TableCell>{rec.file}</TableCell>
                            <TableCell align="right">{rec.size}</TableCell>
                            <TableCell align="right">{new Date(rec.timestamp).toLocaleString()}</TableCell>
                            <TableCell align="center">
                              <Tooltip title="Play">
                                <IconButton onClick={() => handlePlay(rec.file)} color="primary">
                                  <PlayArrowIcon />
                                </IconButton>
                              </Tooltip>
                              <Tooltip title="Download">
                                <IconButton component="a" href={`/tasks/${task.id}/recordings/${rec.file}/mp4?download=true`} color="primary">
                                  <DownloadIcon />
                                </IconButton>
                              </Tooltip>
                            </TableCell>
                          </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </TableContainer>
            )}
          </Paper>
          {playUrl && (
              <Paper sx={{ p: isMobile ? 1 : 2, display: 'flex', justifyContent: 'center', borderRadius: 2, boxShadow: 3 }}>
                <video
                    src={playUrl}
                    controls
                    style={{ width: '100%', borderRadius: '8px' }}
                />
              </Paper>
          )}
        </Box>
      </ThemeProvider>
  );
}

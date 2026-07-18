"use client";

import { useEffect, useState, useRef } from 'react';
import { useTranslation } from 'react-i18next';
import '../i18n';
import { 
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer
} from 'recharts';
import { 
  Link, ExternalLink, Activity, Package, DollarSign, Globe, TrendingUp, Settings, Send, Search, 
  RefreshCw, AlertCircle, Plus, ClipboardList, User, Image as ImageIcon, 
  FileText, CheckSquare, Square, Eye 
, Zap} from 'lucide-react';


const originalFetch = globalThis.fetch;
globalThis.fetch = async (input: RequestInfo | URL, init?: RequestInit) => {
  const customInit = init || {};
  customInit.headers = {
    ...customInit.headers,
    'ngrok-skip-browser-warning': '69420'
  };
  return originalFetch(input, customInit);
};

interface CrawledGroup {
  name: string;
  url: string;
  members?: string;
  posts?: string;
}

interface LibraryContent {
  filename: string;
  preview: string;
}

interface LibraryImage {
  filename: string;
}

const FACEBOOK_PAGES = [
  "Nhà Phân Phối Ly Nhựa Tây Ninh",
  "In Ly Tây Ninh",
  "Geta Oasis - Xe nước lưu động Tây Ninh"
];

export default function Dashboard() {
  const { t, i18n } = useTranslation();
  const [activeTab, setActiveTab] = useState<'dashboard' | 'facebook' | 'research'>('dashboard');
  const [fbSubTab, setFbSubTab] = useState<'content' | 'group' | 'campaign'>('content');
  const [isInitialized, setIsInitialized] = useState(false);
  
  // Campaign configurations states
  const [profileType, setProfileType] = useState<'user' | 'page'>('user');
  const [selectedPage, setSelectedPage] = useState<string>(FACEBOOK_PAGES[0]);
  const [activeProfile, setActiveProfile] = useState<string>('Đang quét tài khoản...');

  // Market Research states
  const [researchQuery, setResearchQuery] = useState('');
  const [researchSources, setResearchSources] = useState<Set<string>>(new Set(['google', 'facebook']));
  const [researchLimits, setResearchLimits] = useState<Record<string, number>>({ google: 10, facebook: 15, maps: 15, tiktok: 4 });
  const [isResearching, setIsResearching] = useState(false);
  const [researchHistory, setResearchHistory] = useState<any[]>([]);
  const [researchResults, setResearchResults] = useState<any>(null);

  const fetchResearchHistory = async () => {
    try {
      const res = await fetch(`${API_URL}/api/facebook/research-history`);
      if (res.ok) {
        const data = await res.json();
        setResearchHistory(data.data || []);
      }
    } catch (e) {
      console.error(e);
    }
  };

  const handleRunResearch = async () => {
    if (!researchQuery) return;
    setIsResearching(true);
    setApiMessage({ type: 'success', text: 'Đang khởi chạy nghiên cứu thị trường...' });
    try {
      const res = await fetch(`${API_URL}/api/facebook/run-research`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          query: researchQuery,
          sources: Array.from(researchSources),
          limits: researchLimits
        })
      });
      const data = await res.json();
      if (res.ok) {
        setApiMessage({ type: 'success', text: data.message });
      } else {
        setApiMessage({ type: 'error', text: data.detail });
      }
    } catch (e) {
      setApiMessage({ type: 'error', text: String(e) });
    }
    setIsResearching(false);
  };

  const viewResearchFile = async (filename: string) => {
    try {
      const res = await fetch(`${API_URL}/api/facebook/research-results/${filename}`);
      if (res.ok) {
        const data = await res.json();
        setResearchResults(data.data);
      }
    } catch (e) {
      console.error(e);
    }
  };

  const deleteResearchFile = async (filename: string) => {
    if (!window.confirm('Bạn có chắc chắn muốn xóa tệp kết quả này?')) return;
    try {
      const res = await fetch(`${API_URL}/api/facebook/research-results/${filename}`, { method: 'DELETE' });
      const data = await res.json();
      if (res.ok) {
        setApiMessage({ type: 'success', text: 'Đã xóa lịch sử nghiên cứu thành công!' });
        if (researchResults?.filename === filename) {
          setResearchResults(null);
        }
        fetchResearchHistory();
      } else {
        setApiMessage({ type: 'error', text: data.detail || 'Lỗi khi xóa tệp' });
      }
    } catch (e) {
      setApiMessage({ type: 'error', text: 'Lỗi kết nối khi xóa tệp' });
      console.error(e);
    }
  };

  const [detectingProfile, setDetectingProfile] = useState<boolean>(false);
  
  // Dashboard states
  const [dashboardData, setDashboardData] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  
  // Basic states
  const [groupsText, setGroupsText] = useState<string>('');
  const [targetGroupsList, setTargetGroupsList] = useState<string[]>([]);
  const [selectedTargetGroups, setSelectedTargetGroups] = useState<Set<string>>(new Set());
  const [searchKeyword, setSearchKeyword] = useState<string>('');
  const [crawlKeyword, setCrawlKeyword] = useState<string>('');
  const [logs, setLogs] = useState<string>('Đang tải nhật ký...');
  const [postedLinks, setPostedLinks] = useState<any>({});
  const [showLinks, setShowLinks] = useState(false);
  const [apiMessage, setApiMessage] = useState<{ type: 'success' | 'error' | 'info', text: string } | null>(null);
  const [activeCeleryTasks, setActiveCeleryTasks] = useState<any[]>([]);

  // Loading indicator states
  const [isSearching, setIsSearching] = useState(false);
  const [isCrawling, setIsCrawling] = useState(false);
  const [isPostingCampaign, setIsPostingCampaign] = useState(false);
  const [isGeneratingContent, setIsGeneratingContent] = useState(false);
  const [isPostingPage, setIsPostingPage] = useState(false);

  // Group crawler states
  const [crawledGroups, setCrawledGroups] = useState<CrawledGroup[]>([]);
  const [selectedCrawledUrls, setSelectedCrawledUrls] = useState<Set<string>>(new Set());
  const [crawledKeywords, setCrawledKeywords] = useState<string[]>([]);
  const [selectedCrawlKeyword, setSelectedCrawlKeyword] = useState<string>('');

  // Campaign configurations states
  const [contentPrompt, setContentPrompt] = useState<string>('');
  const [imagePrompt, setImagePrompt] = useState<string>('');
  const [isEnhancingContent, setIsEnhancingContent] = useState<boolean>(false);
  const [isEnhancingImage, setIsEnhancingImage] = useState<boolean>(false);
  const [isGeneratingContentOnly, setIsGeneratingContentOnly] = useState<boolean>(false);
  const [isGeneratingImageOnly, setIsGeneratingImageOnly] = useState<boolean>(false);
  const [selectedVibe, setSelectedVibe] = useState<string>('professional');
  const [selectedAspectRatio, setSelectedAspectRatio] = useState<string>('1:1');
  const [isStopping, setIsStopping] = useState<boolean>(false);
  
  // Library library states
  const [libraryContents, setLibraryContents] = useState<LibraryContent[]>([]);
  const [libraryImages, setLibraryImages] = useState<LibraryImage[]>([]);
  const [selectedContentFile, setSelectedContentFile] = useState<string>('');
  const [selectedContentText, setSelectedContentText] = useState<string>('');
  const [selectedImageFile, setSelectedImageFile] = useState<string>('');
  const [imageObjectURL, setImageObjectURL] = useState<string>('');
  const [isEditingContent, setIsEditingContent] = useState<boolean>(false);
  const [editingContentText, setEditingContentText] = useState<string>('');

  const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

  // Fetch image via fetch to bypass ngrok browser warning
  useEffect(() => {
    if (selectedImageFile) {
      const url = `${API_URL}/static/images/${selectedImageFile}`;
      fetch(url)
        .then(res => {
          if (!res.ok) throw new Error('Failed to load image');
          return res.blob();
        })
        .then(blob => {
          const objUrl = URL.createObjectURL(blob);
          setImageObjectURL(objUrl);
        })
        .catch(err => {
          console.error(err);
          setImageObjectURL('');
        });
    } else {
      setImageObjectURL('');
    }

    return () => {
      if (imageObjectURL) {
        URL.revokeObjectURL(imageObjectURL);
      }
    };
  }, [selectedImageFile, API_URL]);

  // Fetch full content text when file is selected
  useEffect(() => {
    if (selectedContentFile) {
      setSelectedContentText('Đang tải nội dung...');
      fetch(`${API_URL}/static/content/${selectedContentFile}`)
        .then(res => res.text())
        .then(text => {
          setSelectedContentText(text);
          setEditingContentText(text);
          setIsEditingContent(false);
        })
        .catch(() => setSelectedContentText('Lỗi tải nội dung bài viết.'));
    } else {
      setSelectedContentText('');
      setEditingContentText('');
      setIsEditingContent(false);
    }
  }, [selectedContentFile, API_URL]);

  // Fetch Dashboard data & Facebook Active Profile
  useEffect(() => {
    fetch(`${API_URL}/api/dashboard/metrics`)
      .then(res => res.json())
      .then(resData => {
        if (resData.status === 'success') {
          setDashboardData(resData.data);
        }
        setLoading(false);
      })
      .catch(err => {
        console.error(err);
        setLoading(false);
      });
    fetchActiveProfile();
  }, [API_URL]);

  // Fetch Facebook data when switching to Facebook tab
  useEffect(() => {
    if (activeTab === 'facebook') {
      fetchGroups();
      fetchLogs();
      if (showLinks) fetchPostedLinks();
      fetchCrawledGroups();
      fetchLibrary();
    }
  }, [activeTab]);

  // Polling active background tasks from celery worker
  useEffect(() => {
    const checkTasks = () => {
      fetch(`${API_URL}/api/facebook/active-tasks`)
        .then(res => res.json())
        .then(data => {
          if (data.status === 'success') {
            setActiveCeleryTasks(data.tasks || []);
          }
        })
        .catch(err => console.error('Lỗi khi lấy tác vụ đang chạy:', err));
    };

    checkTasks();
    const interval = setInterval(checkTasks, 2000);
    return () => clearInterval(interval);
  }, [API_URL]);

  const isCelerySearching = activeCeleryTasks.some(t => t.name === 'tasks.run_group_search_join_task');
  const isCeleryCrawling = activeCeleryTasks.some(t => t.name === 'tasks.run_group_crawler_task');
  const isCeleryPostingCampaign = activeCeleryTasks.some(t => t.name === 'tasks.run_group_auto_poster_task' || t.name === 'tasks.run_custom_campaign_task');
  const isCeleryPostingPage = activeCeleryTasks.some(t => t.name === 'tasks.auto_post_facebook');
  const isCeleryResearching = activeCeleryTasks.some(t => t.name === 'tasks.run_market_research_task');
  const isCeleryGeneratingContent = activeCeleryTasks.some(t => t.name === 'tasks.generate_content_only_task');

  const showSearching = isSearching || isCelerySearching;
  const showCrawling = isCrawling || isCeleryCrawling;
  const showPostingCampaign = isPostingCampaign || isCeleryPostingCampaign;
  const showPostingPage = isPostingPage || isCeleryPostingPage;
  const showResearching = isResearching || isCeleryResearching;
  const showGeneratingContent = isGeneratingContent || isCeleryGeneratingContent;

  const isAnyActivityRunning = 
    showSearching || 
    showCrawling || 
    showPostingCampaign || 
    showPostingPage || 
    showResearching || 
    showGeneratingContent ||
    isEnhancingContent || 
    isEnhancingImage || 
    isGeneratingContentOnly || 
    isGeneratingImageOnly || 
    isStopping;

  // Auto refresh logs & research history when tasks are running
  useEffect(() => {
    let interval: NodeJS.Timeout | null = null;

    if (isAnyActivityRunning) {
      fetchLogs();
      if (activeTab === 'research') {
        fetchResearchHistory();
      }
      interval = setInterval(() => {
        fetchLogs();
        if (activeTab === 'research') {
          fetchResearchHistory();
        }
      }, 1500);
    }

    return () => {
      if (interval) clearInterval(interval);
    };
  }, [isAnyActivityRunning, activeTab]);

  // Parse raw groupsText into clean URLs list
  useEffect(() => {
    const list = groupsText
      .split('\n')
      .map(line => line.trim())
      .filter(line => line !== '');
    setTargetGroupsList(list);
    // Mặc định chọn tất cả các group khi tải danh sách
    setSelectedTargetGroups(new Set(list));
  }, [groupsText]);

  const fetchGroups = () => {
    fetch(`${API_URL}/api/facebook/groups`)
      .then(res => res.json())
      .then(data => {
        if (data.status === 'success') {
          setGroupsText(data.groups);
        }
      })
      .catch(err => showMessage('error', 'Không thể kết nối đến máy chủ để tải danh sách nhóm.'));
  };

  const fetchActiveProfile = () => {
    setDetectingProfile(true);
    setActiveProfile('Đang kết nối Chrome...');
    fetch(`${API_URL}/api/facebook/active-profile`)
      .then(res => res.json())
      .then(data => {
        setDetectingProfile(false);
        if (data.status === 'success') {
          setActiveProfile(data.profile);
        } else {
          setActiveProfile(data.message || 'Lỗi quét tài khoản');
        }
      })
      .catch(() => {
        setDetectingProfile(false);
        setActiveProfile('Lỗi kết nối máy chủ gỡ lỗi');
      });
  };

  const fetchPostedLinks = async () => {
    try {
      const res = await fetch(`${API_URL}/api/facebook/posted-links`);
      if (res.ok) {
        const data = await res.json();
        setPostedLinks(data);
      }
    } catch (e) {
      console.error(e);
    }
  };

  const fetchLogs = () => {
    fetch(`${API_URL}/api/facebook/logs`)
      .then(res => res.json())
      .then(data => {
        if (data.status === 'success') {
          setLogs(data.logs);
        }
      })
      .catch(err => setLogs('Lỗi tải nhật ký từ máy chủ.'));
  };

  const getLatestProcessLog = (rawLogs: string) => {
    if (!rawLogs) return null;
    const lines = rawLogs.trim().split('\n');
    for (let i = lines.length - 1; i >= 0; i--) {
      const line = lines[i].trim();
      if (!line || line.includes('===') || line.includes('HOÀN THÀNH') || line.includes('Task finished')) {
        continue;
      }
      if (line.includes('SYSTEM MONITOR') || line.includes('nhiệt độ GPU') || line.includes('hoạt động bình thường')) {
        continue;
      }
      let cleanLine = line.replace(/^\[\d{4}-\d{2}-\d{2}\s\d{2}:\d{2}:\d{2}\]\s*/, '');
      if (cleanLine.length > 5) {
        return cleanLine;
      }
    }
    return null;
  };

  const fetchCrawledGroups = (keyword?: string) => {
    const kw = keyword !== undefined ? keyword : selectedCrawlKeyword;
    const url = kw ? `${API_URL}/api/facebook/crawled-groups?keyword=${encodeURIComponent(kw)}` : `${API_URL}/api/facebook/crawled-groups`;
    fetch(url)
      .then(res => res.json())
      .then(data => {
        if (data.status === 'success') {
          setCrawledGroups(data.data);
          if (data.keywords) {
            setCrawledKeywords(data.keywords);
            if (!keyword && !selectedCrawlKeyword && data.keywords.length > 0) {
              setSelectedCrawlKeyword(data.keywords[0]);
            }
          }
        }
      })
      .catch(err => console.error('Lỗi tải kết quả cào nhóm:', err));
  };

  const fetchLibrary = () => {
    fetch(`${API_URL}/api/facebook/library`)
      .then(res => res.json())
      .then(data => {
        if (data.status === 'success') {
          setLibraryContents(data.contents);
          setLibraryImages(data.images);
        }
      })
      .catch(err => console.error('Lỗi tải thư viện:', err));
  };

  const handleImageUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    const formData = new FormData();
    formData.append('file', file);

    setApiMessage({ type: 'success', text: 'Đang tải hình ảnh lên...' });
    fetch(`${API_URL}/api/facebook/library/upload-image`, {
      method: 'POST',
      body: formData,
    })
      .then(res => res.json())
      .then(data => {
        if (data.status === 'success') {
          setApiMessage({ type: 'success', text: 'Tải ảnh lên thư viện thành công!' });
          fetchLibrary();
        } else {
          setApiMessage({ type: 'error', text: data.detail || 'Lỗi khi tải ảnh lên.' });
        }
      })
      .catch(() => {
        setApiMessage({ type: 'error', text: 'Lỗi kết nối khi tải ảnh.' });
      });
  };

  const handleSaveEditedContent = async () => {
    if (!selectedContentFile) return;
    try {
      const res = await fetch(`${API_URL}/api/facebook/library/save-content/${selectedContentFile}`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'ngrok-skip-browser-warning': 'true'
        },
        body: JSON.stringify({ content: editingContentText })
      });
      const data = await res.json();
      if (res.ok) {
        setSelectedContentText(editingContentText);
        setIsEditingContent(false);
        showMessage('success', 'Đã cập nhật bài viết thành công!');
        fetchLibrary();
      } else {
        showMessage('error', data.detail || 'Lỗi lưu bài viết');
      }
    } catch (err) {
      showMessage('error', 'Không thể kết nối đến máy chủ.');
    }
  };

  const handleDeleteContent = (filename: string) => {
    console.log("handleDeleteContent called with:", filename);
    if (!filename) return;
    
    let shouldDelete = true;
    try {
      shouldDelete = window.confirm(`Bạn có chắc chắn muốn xóa bài viết "${filename}" khỏi thư viện?`);
    } catch (e) {
      console.warn("window.confirm is blocked or failed, bypassing:", e);
    }
    
    if (!shouldDelete) {
      console.log("Delete canceled by user/confirm dialog");
      return;
    }

    console.log("Sending DELETE request for content:", filename);
    fetch(`${API_URL}/api/facebook/library/content/${encodeURIComponent(filename)}`, { method: 'DELETE' })
      .then(res => {
        console.log("Delete content response status:", res.status);
        return res.json();
      })
      .then(data => {
        console.log("Delete content response data:", data);
        if (data.status === 'success') {
          showMessage('success', `Đã xóa bài viết: ${filename}`);
          setSelectedContentFile('');
          fetchLibrary();
        } else {
          showMessage('error', data.detail || 'Lỗi khi xóa bài viết.');
        }
      })
      .catch((err) => {
        console.error("Delete content request failed:", err);
        showMessage('error', 'Lỗi kết nối máy chủ khi xóa bài viết.');
      });
  };

  const handleDeleteImage = (filename: string) => {
    console.log("handleDeleteImage called with:", filename);
    if (!filename) return;
    
    let shouldDelete = true;
    try {
      shouldDelete = window.confirm(`Bạn có chắc chắn muốn xóa hình ảnh "${filename}" khỏi thư viện?`);
    } catch (e) {
      console.warn("window.confirm is blocked or failed, bypassing:", e);
    }
    
    if (!shouldDelete) {
      console.log("Delete canceled by user/confirm dialog");
      return;
    }

    console.log("Sending DELETE request for image:", filename);
    fetch(`${API_URL}/api/facebook/library/image/${encodeURIComponent(filename)}`, { method: 'DELETE' })
      .then(res => {
        console.log("Delete image response status:", res.status);
        return res.json();
      })
      .then(data => {
        console.log("Delete image response data:", data);
        if (data.status === 'success') {
          showMessage('success', `Đã xóa ảnh: ${filename}`);
          setSelectedImageFile('');
          fetchLibrary();
        } else {
          showMessage('error', data.detail || 'Lỗi khi xóa ảnh.');
        }
      })
      .catch((err) => {
        console.error("Delete image request failed:", err);
        showMessage('error', 'Lỗi kết nối máy chủ khi xóa ảnh.');
      });
  };

  const showMessage = (type: 'success' | 'error' | 'info', text: string) => {
    setApiMessage({ type, text });
    setTimeout(() => setApiMessage(null), 3000); // Tự ẩn sau 3s
  };

  const handleSaveGroups = () => {
    fetch(`${API_URL}/api/facebook/groups`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ groups: groupsText })
    })
      .then(res => res.json())
      .then(data => {
        if (data.status === 'success') {
          showMessage('success', data.message);
        } else {
          showMessage('error', 'Lỗi khi lưu danh sách.');
        }
      })
      .catch(() => showMessage('error', 'Lỗi kết nối máy chủ.'));
  };

  const handleRunSearchJoin = (selectedUrls?: string[]) => {
    setIsSearching(true);
    const body = selectedUrls && selectedUrls.length > 0
      ? { urls: selectedUrls }
      : { keyword: selectedCrawlKeyword };
      
    fetch(`${API_URL}/api/facebook/run-search-join`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body)
    })
      .then(res => res.json())
      .then(data => {
        setIsSearching(false);
        if (data.status === 'success') {
          showMessage('success', data.message);
          setTimeout(fetchLogs, 2000);
        }
      })
      .catch(() => {
        setIsSearching(false);
        showMessage('error', 'Lỗi kết nối máy chủ.');
      });
  };

  const handleRunCrawl = () => {
    setIsCrawling(true);
    fetch(`${API_URL}/api/facebook/run-crawl`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ keyword: crawlKeyword })
    })
      .then(res => res.json())
      .then(data => {
        setIsCrawling(false);
        if (data.status === 'success') {
          showMessage('success', data.message);
          setTimeout(fetchLogs, 2000);
          setTimeout(fetchCrawledGroups, 15000);
        }
      })
      .catch(() => {
        setIsCrawling(false);
        showMessage('error', 'Lỗi kết nối máy chủ.');
      });
  };

  const handleEnhancePrompt = async (type: 'content' | 'image') => {
    const prompt = type === 'content' ? contentPrompt : imagePrompt;
    if (!prompt.trim()) {
      showMessage('error', 'Vui lòng nhập mô tả ban đầu trước khi enhance.');
      return;
    }
    
    if (type === 'content') setIsEnhancingContent(true);
    else setIsEnhancingImage(true);
    
    try {
      const res = await fetch(`${API_URL}/api/facebook/enhance-prompt`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ prompt: prompt, type: type })
      });
      const data = await res.json();
      
      if (type === 'content') setIsEnhancingContent(false);
      else setIsEnhancingImage(false);
      
      if (data.status === 'success') {
        if (type === 'content') setContentPrompt(data.enhanced_prompt);
        else setImagePrompt(data.enhanced_prompt);
        showMessage('success', 'Đã nâng cấp prompt thành công!');
      } else {
        showMessage('error', data.detail || 'Lỗi nâng cấp prompt.');
      }
    } catch (error) {
      if (type === 'content') setIsEnhancingContent(false);
      else setIsEnhancingImage(false);
      showMessage('error', 'Lỗi kết nối máy chủ khi enhance.');
    }
  };

    const pollTask = async (taskId: string, successMessage: string) => {
    try {
      const res = await fetch(`${API_URL}/api/facebook/task-status/${taskId}`);
      const data = await res.json();
      if (data.status === 'SUCCESS') {
        showMessage('success', successMessage);
        fetchLibrary();
      } else if (data.status === 'FAILURE') {
        showMessage('error', `Tác vụ thất bại: ${data.result || 'Lỗi không xác định'}`);
      } else {
        // Trạng thái PENDING, STARTED... tiếp tục poll sau 2s
        setTimeout(() => pollTask(taskId, successMessage), 2000);
      }
    } catch (e) {
      console.error('Lỗi khi poll task', e);
    }
  };

  const handleGenerateContentOnly = () => {
    if (!contentPrompt.trim()) {
      showMessage('error', 'Vui lòng nhập mô tả tin đăng.');
      return;
    }
    
    setIsGeneratingContentOnly(true);
    showMessage('info', 'Đang gửi yêu cầu sinh bài viết, tác vụ sẽ chạy ngầm...');
    fetch(`${API_URL}/api/facebook/generate-campaign-content-only`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ keyword: contentPrompt, vibe: selectedVibe })
    })
      .then(res => res.json())
      .then(data => {
        setIsGeneratingContentOnly(false);
        if (data.status === 'success') {
          setContentPrompt('');
          setTimeout(fetchLogs, 2000);
          if (data.task_id) {
            pollTask(data.task_id, 'Đã sinh nội dung bài viết thành công!');
          } else {
            showMessage('success', data.message);
            setTimeout(fetchLibrary, 10000);
          }
        }
      })
      .catch(() => {
        setIsGeneratingContentOnly(false);
        showMessage('error', 'Lỗi kết nối máy chủ.');
      });
  };

  const handleGenerateImageOnly = () => {
    if (!imagePrompt.trim()) {
      showMessage('error', 'Vui lòng nhập mô tả ảnh.');
      return;
    }
    
    setIsGeneratingImageOnly(true);
    showMessage('info', 'Đang gửi yêu cầu vẽ ảnh (Imagen 3), tác vụ sẽ chạy ngầm...');
    fetch(`${API_URL}/api/facebook/generate-campaign-image-only`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ keyword: imagePrompt, aspect_ratio: selectedAspectRatio })
    })
      .then(res => res.json())
      .then(data => {
        setIsGeneratingImageOnly(false);
        if (data.status === 'success') {
          setImagePrompt('');
          setTimeout(fetchLogs, 2000);
          if (data.task_id) {
            pollTask(data.task_id, 'Đã vẽ ảnh AI thành công!');
          } else {
            showMessage('success', data.message);
            setTimeout(fetchLibrary, 10000);
          }
        }
      })
      .catch(() => {
        setIsGeneratingImageOnly(false);
        showMessage('error', 'Lỗi kết nối máy chủ.');
      });
  };

  const handleStopTasks = () => {
    if (!window.confirm("Bạn có chắc chắn muốn dừng khẩn cấp tất cả các tác vụ đăng bài, cào nhóm và tham gia nhóm đang chạy không?")) {
      return;
    }
    setIsStopping(true);
    fetch(`${API_URL}/api/facebook/stop-tasks`, { method: 'POST' })
      .then(res => res.json())
      .then(data => {
        setIsStopping(false);
        if (data.status === 'success') {
          showMessage('success', data.message);
          setTimeout(fetchLogs, 1000);
        } else {
          showMessage('error', data.message || 'Lỗi dừng tác vụ.');
        }
      })
      .catch(() => {
        setIsStopping(false);
        showMessage('error', 'Lỗi kết nối máy chủ.');
      });
  };

  const handleRunCampaign = () => {
    if (selectedTargetGroups.size === 0) {
      showMessage('error', 'Vui lòng tích chọn ít nhất 1 group mục tiêu để đăng bài!');
      return;
    }

    setIsPostingCampaign(true);
    fetch(`${API_URL}/api/facebook/run-campaign`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        profile_type: profileType,
        page_name: profileType === 'page' ? selectedPage : '',
        content_source: selectedContentFile ? 'library' : 'manual',
        content_file: selectedContentFile,
        image_source: selectedImageFile ? 'library' : 'none',
        image_file: selectedImageFile,
        groups: Array.from(selectedTargetGroups)
      })
    })
      .then(res => res.json())
      .then(data => {
        setIsPostingCampaign(false);
        if (data.status === 'success') {
          showMessage('success', data.message);
          setTimeout(fetchLogs, 2000);
        }
      })
      .catch(() => {
        setIsPostingCampaign(false);
        showMessage('error', 'Lỗi kết nối máy chủ.');
      });
  };

  const handleRunPagePoster = () => {
    setIsPostingPage(true);
    fetch(`${API_URL}/api/facebook/run-page-poster`, { method: 'POST' })
      .then(res => res.json())
      .then(data => {
        setIsPostingPage(false);
        if (data.status === 'success') {
          showMessage('success', data.message);
        }
      })
      .catch(() => {
        setIsPostingPage(false);
        showMessage('error', 'Lỗi kết nối máy chủ.');
      });
  };

  const handleSelectCrawled = (url: string) => {
    const newSelected = new Set(selectedCrawledUrls);
    if (newSelected.has(url)) {
      newSelected.delete(url);
    } else {
      newSelected.add(url);
    }
    setSelectedCrawledUrls(newSelected);
  };

  const handleSelectAllCrawled = () => {
    if (selectedCrawledUrls.size === crawledGroups.length) {
      setSelectedCrawledUrls(new Set());
    } else {
      setSelectedCrawledUrls(new Set(crawledGroups.map(g => g.url)));
    }
  };

  const handleImportSelected = () => {
    if (selectedCrawledUrls.size === 0) return;
    
    fetch(`${API_URL}/api/facebook/import-groups`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ urls: Array.from(selectedCrawledUrls) })
    })
      .then(res => res.json())
      .then(data => {
        if (data.status === 'success') {
          showMessage('success', data.message);
          fetchGroups();
          setSelectedCrawledUrls(new Set());
        }
      })
      .catch(() => showMessage('error', 'Lỗi kết nối máy chủ.'));
  };

  const handleToggleTargetGroup = (url: string) => {
    const newSelected = new Set(selectedTargetGroups);
    if (newSelected.has(url)) {
      newSelected.delete(url);
    } else {
      newSelected.add(url);
    }
    setSelectedTargetGroups(newSelected);
  };

  const handleToggleAllTargetGroups = () => {
    if (selectedTargetGroups.size === targetGroupsList.length) {
      setSelectedTargetGroups(new Set());
    } else {
      setSelectedTargetGroups(new Set(targetGroupsList));
    }
  };

  if (loading) return <div className="min-h-screen flex items-center justify-center text-slate-800 bg-white">{t('loading')}</div>;
  if (!dashboardData) return <div className="min-h-screen flex items-center justify-center text-red-600 bg-white">{t('error')}</div>;

  if (!isInitialized) {
    return (
      <div className="min-h-screen bg-white text-slate-900 flex items-center justify-center p-6 font-sans">
        <div className="w-full max-w-md bg-white border border-slate-200 rounded-2xl p-8 shadow-md space-y-6">
          <div className="text-center">
            <h1 className="text-2xl font-bold text-slate-800">Cấu Hình Tài Khoản Đăng Bài</h1>
            <p className="text-slate-500 text-sm mt-1">Chọn tư cách tài khoản trước khi vào hệ thống chính</p>
          </div>
          
          <div className="space-y-4">
            {/* Active Profile Info */}
            <div className="p-4 bg-slate-50 border border-slate-200 rounded-xl flex items-center justify-between shadow-sm">
              <div className="min-w-0 flex-1">
                <span className="text-[10px] font-bold text-slate-400 uppercase tracking-wider block">Nick đang mở trên Chrome:</span>
                <span className="text-sm font-bold text-slate-800 flex items-center gap-1.5 mt-1 truncate">
                  {detectingProfile ? (
                    <>
                      <RefreshCw className="animate-spin text-blue-600" size={14} />
                      <span className="text-slate-500 font-medium">Đang kiểm tra kết nối...</span>
                    </>
                  ) : (
                    <>
                      <span className="truncate">👤 {activeProfile}</span>
                    </>
                  )}
                </span>
              </div>
              <button 
                onClick={fetchActiveProfile}
                disabled={detectingProfile}
                className="p-2 text-blue-600 hover:bg-slate-200 rounded-lg transition-colors flex-shrink-0 ml-2"
                title="Quét lại"
              >
                <RefreshCw size={16} className={detectingProfile ? "animate-spin" : ""} />
              </button>
            </div>

            <div className="flex gap-4">
              <label className={`flex items-center gap-2 cursor-pointer px-4 py-3 rounded-xl border transition-colors flex-1 ${profileType === 'user' ? 'border-blue-600 bg-blue-50/50' : 'border-slate-200 bg-white hover:border-slate-300'}`}>
                <input 
                  type="radio" 
                  name="initProfileType" 
                  checked={profileType === 'user'} 
                  onChange={() => setProfileType('user')}
                  className="w-4 h-4 accent-blue-600"
                />
                <span className="text-sm font-semibold text-slate-700">Nick Cá Nhân</span>
              </label>
              <label className={`flex items-center gap-2 cursor-pointer px-4 py-3 rounded-xl border transition-colors flex-1 ${profileType === 'page' ? 'border-blue-600 bg-blue-50/50' : 'border-slate-200 bg-white hover:border-slate-300'}`}>
                <input 
                  type="radio" 
                  name="initProfileType" 
                  checked={profileType === 'page'} 
                  onChange={() => setProfileType('page')}
                  className="w-4 h-4 accent-blue-600"
                />
                <span className="text-sm font-semibold text-slate-700">Trang (Fanpage)</span>
              </label>
            </div>

            {profileType === 'page' && (
              <div className="space-y-1.5 animate-fade-in">
                <label className="text-xs font-bold text-slate-500 uppercase tracking-wider">Chọn trang quản lý:</label>
                <select 
                  value={selectedPage} 
                  onChange={(e) => setSelectedPage(e.target.value)}
                  className="w-full px-4 py-3 bg-white border border-slate-200 rounded-xl focus:border-blue-600 focus:outline-none transition-colors text-slate-700 text-sm font-medium shadow-sm"
                >
                  {FACEBOOK_PAGES.map((page, idx) => (
                     <option key={idx} value={page}>{page}</option>
                  ))}
                </select>
              </div>
            )}
          </div>

          <button 
            onClick={() => setIsInitialized(true)}
            className="w-full py-3 bg-blue-600 hover:bg-blue-500 text-white font-bold rounded-xl transition-all shadow-sm flex items-center justify-center gap-2"
          >
            Vào giao diện chính
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-slate-50 text-slate-900 p-8 font-sans selection:bg-blue-100">
      <div className="max-w-[1800px] mx-auto space-y-8">
        
        {/* Header */}
        <div className="flex justify-between items-center bg-white p-6 rounded-2xl border border-slate-200 shadow-sm">
          <div>
            <h1 className="text-3xl font-extrabold text-slate-900">
              Geta Automation
            </h1>
            <p className="text-slate-500 mt-1">
              {activeTab === 'dashboard' ? 'Hệ thống báo cáo chỉ số tự động hóa' : 'Hệ thống tự động hóa marketing & quản lý kho'}
            </p>
          </div>
          
          <div className="flex items-center gap-4">
            {/* Tabs */}
            <div className="bg-slate-100 p-1.5 rounded-xl border border-slate-200 flex gap-1">
              <button 
                onClick={() => setActiveTab('dashboard')}
                className={`px-4 py-2 rounded-lg text-sm font-semibold transition-all ${activeTab === 'dashboard' ? 'bg-blue-600 text-white shadow-sm' : 'text-slate-600 hover:text-slate-950'}`}
              >
                📊 Báo cáo
              </button>
              <button 
                onClick={() => setActiveTab('facebook')}
                className={`px-4 py-2 rounded-lg text-sm font-semibold transition-all ${activeTab === 'facebook' ? 'bg-blue-600 text-white shadow-sm' : 'text-slate-600 hover:text-slate-950'}`}
              >
                🎨 Facebook Campaign
              </button>
                          <button 
                onClick={() => { setActiveTab('research'); fetchResearchHistory(); }}
                className={`px-4 py-2 rounded-lg text-sm font-semibold transition-all ${activeTab === 'research' ? 'bg-blue-600 text-white shadow-sm' : 'text-slate-600 hover:text-slate-950'}`}
              >
                🔍 Nghiên cứu
              </button>
            </div>

            {/* Language Switcher */}
            <button 
              onClick={() => i18n.changeLanguage(i18n.language === 'vi' ? 'en' : 'vi')}
              className="flex items-center gap-2 px-4 py-2 bg-slate-200 hover:bg-slate-300 rounded-xl transition-all border border-slate-200 font-semibold"
            >
              <Globe size={18} className="text-blue-600" />
              <span>{i18n.language === 'vi' ? 'EN' : 'VI'}</span>
            </button>
          </div>
        </div>

        {/* Global Toast Alert */}
        {apiMessage && (
          <div className={`p-4 rounded-xl border flex items-center gap-3 animate-fade-in ${apiMessage.type === 'success' ? 'bg-green-50 border-green-200 text-green-800' : 'bg-red-50 border-red-200 text-red-800'}`}>
            <AlertCircle size={20} className={apiMessage.type === 'success' ? 'text-green-600' : 'text-red-600'} />
            <span className="font-medium">{apiMessage.text}</span>
          </div>
        )}

        {/* Active Task Process Indicator */}
        {isAnyActivityRunning && (
          <div className="bg-blue-50 border border-blue-200 p-5 rounded-2xl shadow-sm flex flex-col md:flex-row md:items-center justify-between gap-4 animate-pulse">
            <div className="flex items-center gap-3">
              <div className="p-2.5 bg-blue-600 text-white rounded-xl">
                <RefreshCw size={22} className="animate-spin" />
              </div>
              <div className="space-y-1">
                <h3 className="text-base font-bold text-slate-800">Hệ thống đang xử lý tác vụ...</h3>
                <p className="text-slate-500 text-xs font-medium">
                  {showSearching && "🔍 Đang tự động tìm kiếm và tham gia nhóm..."}
                  {showCrawling && "📋 Đang cào thông tin danh sách nhóm..."}
                  {showPostingCampaign && "🚀 Đang đăng bài hàng loạt lên các nhóm..."}
                  {showGeneratingContent && "✨ AI đang sinh bài viết và hình ảnh minh họa..."}
                  {showPostingPage && "📢 Đang tự động đăng bài trực tiếp lên các Fanpage..."}
                  {isEnhancingContent && "✍️ AI đang nâng cấp văn bản bài viết (Enhance Content)..."}
                  {isEnhancingImage && "🎨 AI đang nâng cấp mô tả hình ảnh (Enhance Image Prompt)..."}
                  {isGeneratingContentOnly && "📝 AI đang viết nội dung tin đăng..."}
                  {isGeneratingImageOnly && "🖼️ AI đang tiến hành vẽ ảnh minh họa với Imagen 3..."}
                  {showResearching && "🔍 AI đang chạy nghiên cứu thị trường diện rộng..."}
                  {isStopping && "🛑 Đang gửi yêu cầu dừng các tác vụ..."}
                </p>
                {getLatestProcessLog(logs) && (
                  <div className="mt-1.5 flex items-center gap-2 bg-slate-900 text-green-400 font-mono text-[10px] px-3 py-1.5 rounded-lg border border-slate-950 w-fit max-w-full overflow-hidden shadow-inner">
                    <span className="w-1.5 h-1.5 rounded-full bg-green-500 animate-pulse"></span>
                    <span>AI Thinking: {getLatestProcessLog(logs)}</span>
                  </div>
                )}
              </div>
            </div>
            <div className="flex items-center gap-2">
              <span className="inline-flex items-center px-3 py-1 rounded-full text-xs font-semibold bg-blue-100 text-blue-800 border border-blue-200">
                <span className="w-1.5 h-1.5 rounded-full bg-blue-600 mr-1.5 animate-ping"></span>
                Processing
              </span>
            </div>
          </div>
        )}

        {activeTab === 'dashboard' && (
          /* ==================== DASHBOARD TAB ==================== */
          <>
            {/* Stats Row */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              <div className="bg-white p-6 rounded-2xl border border-slate-200 shadow-sm flex items-center gap-4 hover:border-cyan-500 transition-colors">
                <div className="p-4 bg-cyan-100 rounded-xl text-cyan-600">
                  <DollarSign size={28} />
                </div>
                <div>
                  <p className="text-slate-500 text-sm font-medium">{t('total_revenue')}</p>
                  <p className="text-2xl font-bold text-slate-800">{new Intl.NumberFormat('vi-VN', { style: 'currency', currency: 'VND' }).format(dashboardData.summary.total_revenue)}</p>
                </div>
              </div>
              
              <div className="bg-white p-6 rounded-2xl border border-slate-200 shadow-sm flex items-center gap-4 hover:border-purple-500 transition-colors">
                <div className="p-4 bg-purple-100 rounded-xl text-purple-600">
                  <Activity size={28} />
                </div>
                <div>
                  <p className="text-slate-500 text-sm font-medium">{t('total_orders')}</p>
                  <p className="text-2xl font-bold text-slate-800">{dashboardData.summary.total_orders}</p>
                </div>
              </div>
            </div>

            {/* Charts Row */}
            <div className="grid grid-cols-1 gap-8">
              {/* Inventory Table */}
              <div className="bg-white p-6 rounded-2xl border border-slate-200 shadow-sm">
                <h2 className="text-xl font-bold mb-6 flex items-center gap-2 text-slate-800">
                  <Package size={20} className="text-cyan-600" />
                  Tồn Kho Thực Tế (Supabase)
                </h2>
                <div className="overflow-x-auto">
                  <table className="w-full text-left border-collapse">
                    <thead>
                      <tr className="border-b border-slate-200 text-slate-500 text-sm">
                        <th className="pb-3 font-semibold">{t('product')}</th>
                        <th className="pb-3 font-semibold">{t('stock')}</th>
                        <th className="pb-3 font-semibold">Giá gần nhất</th>
                        <th className="pb-3 font-semibold">Tổng giá trị</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-100">
                      {dashboardData.inventory.map((item: any, idx: number) => (
                        <tr key={idx} className="hover:bg-slate-50 transition-colors">
                          <td className="py-4 text-slate-700 font-medium">{item.name}</td>
                          <td className="py-4">
                            <span className={`px-2.5 py-1 rounded-full text-xs font-semibold ${item.stock > 10 ? 'bg-green-50 text-green-700 border border-green-200' : 'bg-red-50 text-red-700 border border-red-200'}`}>
                              {item.stock}
                            </span>
                          </td>
                          <td className="py-4 text-slate-600">
                            {new Intl.NumberFormat('vi-VN', { style: 'currency', currency: 'VND' }).format(item.price)}
                          </td>
                          <td className="py-4 text-slate-800 font-semibold">
                            {new Intl.NumberFormat('vi-VN', { style: 'currency', currency: 'VND' }).format(item.stock * item.price)}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            </div>

            {/* Recent Inventory Transactions */}
            {dashboardData.recent_transactions && dashboardData.recent_transactions.length > 0 && (
              <div className="bg-white p-6 rounded-2xl border border-slate-200 shadow-sm mt-8">
                <h2 className="text-xl font-bold mb-6 flex items-center gap-2 text-slate-800">
                  <ClipboardList size={20} className="text-cyan-600" />
                  Lịch Sử Xuất Nhập Kho Gần Đây (Supabase)
                </h2>
                <div className="overflow-x-auto">
                  <table className="w-full text-left border-collapse text-sm">
                    <thead>
                      <tr className="border-b border-slate-200 text-slate-500 font-semibold">
                        <th className="pb-3">Thời gian</th>
                        <th className="pb-3">Sản phẩm</th>
                        <th className="pb-3">Loại</th>
                        <th className="pb-3 text-right">Số lượng</th>
                        <th className="pb-3 text-right">Đơn giá</th>
                        <th className="pb-3 text-right">Thành tiền</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-100">
                      {dashboardData.recent_transactions.map((tx: any, idx: number) => (
                        <tr key={idx} className="hover:bg-slate-50 transition-colors">
                          <td className="py-3.5 text-slate-500 text-xs">
                            {new Date(tx.created_at).toLocaleString('vi-VN')}
                          </td>
                          <td className="py-3.5 text-slate-700 font-medium">{tx.item_name}</td>
                          <td className="py-3.5">
                            <span className={`px-2 py-0.5 rounded-full text-xs font-semibold ${tx.type === 'IN' || tx.type === 'IMPORT' ? 'bg-emerald-50 text-emerald-700 border border-emerald-200' : 'bg-rose-50 text-rose-700 border border-rose-200'}`}>
                              {tx.type === 'IN' || tx.type === 'IMPORT' ? 'Nhập kho' : 'Xuất kho'}
                            </span>
                          </td>
                          <td className="py-3.5 text-right font-mono text-slate-600">{tx.quantity}</td>
                          <td className="py-3.5 text-right font-mono text-slate-600">
                            {new Intl.NumberFormat('vi-VN', { style: 'currency', currency: 'VND' }).format(tx.unit_price)}
                          </td>
                          <td className="py-3.5 text-right font-mono font-semibold text-slate-800">
                            {new Intl.NumberFormat('vi-VN', { style: 'currency', currency: 'VND' }).format(tx.total_amount)}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}
          </>
        )}

        {activeTab === 'facebook' && (
          /* ==================== FACEBOOK CAMPAIGN TAB ==================== */
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-8 animate-fade-in">
            {/* FB Sub-navigation */}
            <div className="flex p-1 bg-slate-100 rounded-xl w-fit border border-slate-200 mb-6 col-span-full">
              <button 
                onClick={() => setFbSubTab('content')}
                className={`px-5 py-2.5 rounded-lg text-sm font-bold transition-all flex items-center gap-2 ${fbSubTab === 'content' ? 'bg-white text-blue-600 shadow-sm' : 'text-slate-500 hover:text-slate-700 hover:bg-slate-200/50'}`}
              >
                <FileText size={16} />
                AI Content & Thư Viện
              </button>
              <button 
                onClick={() => setFbSubTab('group')}
                className={`px-5 py-2.5 rounded-lg text-sm font-bold transition-all flex items-center gap-2 ${fbSubTab === 'group' ? 'bg-white text-blue-600 shadow-sm' : 'text-slate-500 hover:text-slate-700 hover:bg-slate-200/50'}`}
              >
                <Search size={16} />
                Quản Lý Group
              </button>
              <button 
                onClick={() => setFbSubTab('campaign')}
                className={`px-5 py-2.5 rounded-lg text-sm font-bold transition-all flex items-center gap-2 ${fbSubTab === 'campaign' ? 'bg-white text-blue-600 shadow-sm' : 'text-slate-500 hover:text-slate-700 hover:bg-slate-200/50'}`}
              >
                <Send size={16} />
                Chiến Dịch Đăng Bài
              </button>
            </div>

            
            {/* Left Side: Campaign Settings & Generator (8 cols) */}
            <div className={`${fbSubTab === 'content' ? 'lg:col-span-12' : 'lg:col-span-8'} space-y-6`}>
              
              {/* Campaign Configurations Card */}
              {fbSubTab === 'campaign' && (
              <div className="bg-white p-6 rounded-2xl border border-slate-200 shadow-sm space-y-6">
                <h2 className="text-xl font-bold flex items-center gap-2 border-b border-slate-100 pb-3 text-slate-800">
                  <Settings size={22} className="text-cyan-600" />
                  Cấu Hình Chiến Dịch Đăng Bài
                </h2>

                <div className="grid grid-cols-1 gap-6">
                  {/* Profile Selection */}
                  <div className="space-y-3">
                    <label className="text-sm font-semibold text-slate-700 flex items-center gap-1.5">
                      <User size={16} className="text-blue-600" />
                      1. Tài Khoản Đăng Bài Đang Chọn:
                    </label>
                    <div className="bg-slate-50 px-4 py-3.5 rounded-xl border border-slate-200 flex justify-between items-center shadow-sm">
                      <span className="text-sm font-bold text-slate-800">
                        {profileType === 'user' ? `👤 Nick Cá Nhân: ${activeProfile}` : `📄 Trang: ${selectedPage}`}
                      </span>
                      <button 
                        onClick={() => setIsInitialized(false)}
                        className="px-2.5 py-1 bg-white hover:bg-slate-50 text-blue-600 border border-slate-200 text-xs font-bold rounded-lg transition-colors shadow-sm"
                      >
                        Thay đổi
                      </button>
                    </div>
                  </div>
                </div>

                {/* Library Selection */}
                <div className="grid grid-cols-1 md:grid-cols-2 gap-6 pt-4 border-t border-slate-100">
                  {/* Select Content file */}
                  <div className="space-y-2">
                    <label className="text-sm font-semibold text-slate-700 flex items-center gap-1.5">
                      <FileText size={16} className="text-cyan-600" />
                      2. Chọn Nội Dung Bài Viết (Content):
                    </label>
                    <select 
                      value={selectedContentFile} 
                      onChange={(e) => setSelectedContentFile(e.target.value)}
                      className="w-full px-4 py-3 bg-white border border-slate-200 rounded-xl focus:border-cyan-500 focus:outline-none text-xs text-slate-700 shadow-sm"
                    >
                      <option value="">-- Chọn bài viết trong thư viện (Hoặc mặc định) --</option>
                      {libraryContents.map((c, idx) => (
                        <option key={idx} value={c.filename}>{c.filename} ({c.preview.slice(0, 30)}...)</option>
                      ))}
                    </select>
                  </div>

                  {/* Select Image file */}
                  <div className="space-y-2">
                    <label className="text-sm font-semibold text-slate-700 flex items-center gap-1.5">
                      <ImageIcon size={16} className="text-blue-600" />
                      3. Chọn Ảnh Đính Kèm:
                    </label>
                    <select 
                      value={selectedImageFile} 
                      onChange={(e) => setSelectedImageFile(e.target.value)}
                      className="w-full px-4 py-3 bg-white border border-slate-200 rounded-xl focus:border-blue-600 focus:outline-none text-xs text-slate-700 shadow-sm"
                    >
                      <option value="">-- Không đính kèm ảnh --</option>
                      {libraryImages.map((img, idx) => (
                        <option key={idx} value={img.filename}>{img.filename}</option>
                      ))}
                    </select>
                  </div>
                </div>

                {/* Run Campaign Button */}
                <div className="pt-4 border-t border-slate-100">
                  <button 
                    onClick={handleRunCampaign}
                    disabled={isPostingCampaign}
                    className="w-full py-4 bg-blue-600 hover:bg-blue-500 text-white font-bold rounded-xl transition-all shadow-md hover:shadow-lg flex items-center justify-center gap-2 disabled:opacity-50 text-base"
                  >
                    {isPostingCampaign ? <RefreshCw className="animate-spin" size={20} /> : <Send size={20} />}
                    <span>BẮT ĐẦU CHẠY CHIẾN DỊCH ĐĂNG BÀI NHÓM</span>
                  </button>
                </div>
              </div>
              )}

              {/* AI Content and Image Generator Cards */}
              {fbSubTab === 'content' && (
              <div className="grid grid-cols-1 xl:grid-cols-2 gap-6">
                
                {/* 1. Sinh Content Card */}
                <div className="bg-white p-6 rounded-2xl border border-slate-200 shadow-sm space-y-4">
                  <h2 className="text-lg font-bold flex items-center gap-2 text-slate-800">
                    <FileText size={18} className="text-blue-600" />
                    Sinh Nội Dung Bài Viết
                  </h2>
                  <p className="text-slate-500 text-xs">
                    Nhập ý tưởng ngắn gọn, sau đó dùng ✨ Enhance Prompt để AI viết lại mô tả chi tiết hơn trước khi sinh bài.
                  </p>
                  <textarea 
                    value={contentPrompt}
                    onChange={(e) => setContentPrompt(e.target.value)}
                    className="w-full p-4 bg-slate-50 border border-slate-200 rounded-xl focus:border-blue-600 focus:bg-white focus:outline-none transition-all text-slate-800 text-sm shadow-inner h-32 resize-y"
                    placeholder="VD: Cần bán 2 lô đất ở Bình Dương, giá 1 tỷ/nền..."
                  />
                  <div className="flex flex-col sm:flex-row gap-3 justify-between items-stretch sm:items-center">
                    <div className="flex items-center gap-2">
                      <span className="text-xs font-semibold text-slate-500 whitespace-nowrap">Vibe văn phong:</span>
                      <select
                        value={selectedVibe}
                        onChange={(e) => setSelectedVibe(e.target.value)}
                        className="px-3 py-2 bg-white border border-slate-200 rounded-lg focus:border-blue-600 focus:outline-none text-slate-700 text-xs font-semibold shadow-sm cursor-pointer"
                      >
                        <option value="professional">💼 Chuyên nghiệp</option>
                        <option value="humorous">😂 Hài hước</option>
                        <option value="sales">💰 Bán hàng</option>
                        <option value="recruitment">📢 Tuyển dụng</option>
                        <option value="casual">🤝 Gần gũi</option>
                      </select>
                    </div>
                    <div className="flex gap-2">
                      <button 
                        onClick={() => handleEnhancePrompt('content')}
                        disabled={isEnhancingContent}
                        className="px-4 py-2 bg-indigo-50 hover:bg-indigo-100 text-indigo-700 font-semibold rounded-lg transition-all flex items-center gap-2 disabled:opacity-50 text-xs shadow-sm border border-indigo-200"
                      >
                        {isEnhancingContent ? <RefreshCw className="animate-spin" size={14} /> : <Zap size={14} className="text-amber-500" />}
                        Enhance
                      </button>
                      <button 
                        onClick={handleGenerateContentOnly}
                        disabled={isGeneratingContentOnly}
                        className="px-4 py-2 bg-blue-600 hover:bg-blue-500 text-white font-semibold rounded-lg transition-all flex items-center gap-2 disabled:opacity-50 text-xs shadow-sm"
                      >
                        {isGeneratingContentOnly ? <RefreshCw className="animate-spin" size={14} /> : <Plus size={14} />}
                        Sinh Content
                      </button>
                    </div>
                  </div>
                </div>

                {/* 2. Sinh Image Card */}
                <div className="bg-white p-6 rounded-2xl border border-slate-200 shadow-sm space-y-4">
                  <h2 className="text-lg font-bold flex items-center gap-2 text-slate-800">
                    <ImageIcon size={18} className="text-blue-600" />
                    Sinh Ảnh Minh Họa (Imagen 3)
                  </h2>
                  <p className="text-slate-500 text-xs">
                    Nhập ý tưởng hình ảnh, sau đó dùng ✨ Enhance Prompt để AI thêm các chi tiết nghệ thuật, ánh sáng, màu sắc.
                  </p>
                  <textarea 
                    value={imagePrompt}
                    onChange={(e) => setImagePrompt(e.target.value)}
                    className="w-full p-4 bg-slate-50 border border-slate-200 rounded-xl focus:border-blue-600 focus:bg-white focus:outline-none transition-all text-slate-800 text-sm shadow-inner h-32 resize-y"
                    placeholder="VD: Một tòa nhà văn phòng hiện đại giữa thành phố..."
                  />
                  <div className="flex flex-col sm:flex-row gap-3 justify-between items-stretch sm:items-center">
                    <div className="flex items-center gap-2">
                      <span className="text-xs font-semibold text-slate-500 whitespace-nowrap">Tỉ lệ ảnh:</span>
                      <select
                        value={selectedAspectRatio}
                        onChange={(e) => setSelectedAspectRatio(e.target.value)}
                        className="px-3 py-2 bg-white border border-slate-200 rounded-lg focus:border-blue-600 focus:outline-none text-slate-700 text-xs font-semibold shadow-sm cursor-pointer"
                      >
                        <option value="1:1">⬜ 1:1</option>
                        <option value="16:9">📺 16:9</option>
                        <option value="4:3">🖥️ 4:3</option>
                        <option value="3:4">📱 3:4</option>
                      </select>
                    </div>
                    <div className="flex gap-2">
                      <button 
                        onClick={() => handleEnhancePrompt('image')}
                        disabled={isEnhancingImage}
                        className="px-4 py-2 bg-indigo-50 hover:bg-indigo-100 text-indigo-700 font-semibold rounded-lg transition-all flex items-center gap-2 disabled:opacity-50 text-xs shadow-sm border border-indigo-200"
                      >
                        {isEnhancingImage ? <RefreshCw className="animate-spin" size={14} /> : <Zap size={14} className="text-amber-500" />}
                        Enhance
                      </button>
                      <button 
                        onClick={handleGenerateImageOnly}
                        disabled={isGeneratingImageOnly}
                        className="px-4 py-2 bg-blue-600 hover:bg-blue-500 text-white font-semibold rounded-lg transition-all flex items-center gap-2 disabled:opacity-50 text-xs shadow-sm"
                      >
                        {isGeneratingImageOnly ? <RefreshCw className="animate-spin" size={14} /> : <Plus size={14} />}
                        Vẽ Ảnh AI
                      </button>
                    </div>
                  </div>
                </div>
                
              </div>
              )}

              {/* Crawl and Join Group Cards */}
              {fbSubTab === 'group' && (
              <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                
                {/* Group Crawler */}
                <div className="bg-white p-6 rounded-2xl border border-slate-200 shadow-sm space-y-4">
                  <h2 className="text-lg font-bold flex items-center gap-2 text-slate-800">
                    <ClipboardList size={18} className="text-blue-600" />
                    Thu Thập Group
                  </h2>
                  <p className="text-xs text-slate-500">
                    Crawl hàng loạt link Group theo từ khóa để lấy thông tin chọn lọc trước.
                  </p>
                  <div className="flex gap-2">
                    <input 
                      type="text" 
                      value={crawlKeyword}
                      onChange={(e) => setCrawlKeyword(e.target.value)}
                      className="flex-1 px-3 py-2 bg-white border border-slate-200 rounded-lg focus:border-blue-600 focus:outline-none text-xs text-slate-800 shadow-sm"
                      placeholder="Crawl từ khóa..."
                    />
                    <button 
                      onClick={handleRunCrawl}
                      disabled={isCrawling}
                      className="px-4 py-2 bg-blue-600 hover:bg-blue-500 text-white font-bold rounded-lg text-xs transition-all flex items-center gap-1 disabled:opacity-50 shadow-sm"
                    >
                      {isCrawling ? <RefreshCw className="animate-spin" size={12} /> : <Search size={12} />}
                      <span>Crawl</span>
                    </button>
                  </div>
                </div>

                {/* Auto Join */}
                <div className="bg-white p-6 rounded-2xl border border-slate-200 shadow-sm space-y-4">
                  <h2 className="text-lg font-bold flex items-center gap-2 text-slate-800">
                    <Search size={18} className="text-blue-600" />
                    Auto Join Group
                  </h2>
                  <p className="text-slate-500 text-[11px] leading-relaxed">
                    Tự động gửi yêu cầu tham gia các nhóm từ danh sách từ khóa đã cào.
                  </p>
                  {crawledKeywords.length > 0 && (
                    <div className="space-y-1">
                      <label className="text-[10px] font-semibold text-slate-400 uppercase tracking-wider block">Chọn từ khóa đã cào</label>
                      <select 
                        value={selectedCrawlKeyword} 
                        onChange={(e) => {
                          setSelectedCrawlKeyword(e.target.value);
                          fetchCrawledGroups(e.target.value);
                        }}
                        className="w-full px-3 py-2 bg-white border border-slate-200 rounded-lg focus:border-blue-600 focus:outline-none text-xs text-slate-800 shadow-sm font-medium"
                      >
                        {crawledKeywords.map((kw) => (
                          <option key={kw} value={kw}>{kw}</option>
                        ))}
                      </select>
                    </div>
                  )}
                  <button 
                    onClick={() => handleRunSearchJoin()}
                    disabled={isSearching || !selectedCrawlKeyword}
                    className="w-full py-2.5 bg-blue-600 hover:bg-blue-500 text-white font-bold rounded-lg text-xs transition-all flex items-center justify-center gap-1 disabled:opacity-50 shadow-sm"
                  >
                    {isSearching ? <RefreshCw className="animate-spin" size={12} /> : <Plus size={12} />}
                    <span>Bắt đầu tự động tham gia nhóm ({selectedCrawlKeyword || 'Chưa chọn từ khóa'})</span>
                  </button>
                </div>

              </div>
              )}

              {/* Crawled Results Table */}
              {fbSubTab === 'group' && crawledGroups.length > 0 && (
                <div className="bg-white p-6 rounded-2xl border border-slate-200 shadow-sm space-y-4">
                  <div className="flex justify-between items-center">
                    <h3 className="text-sm font-bold text-slate-800">
                      Kết quả Crawl mới nhất ({crawledGroups.length} nhóm):
                    </h3>
                    <div className="flex gap-2">
                      <button 
                        onClick={handleSelectAllCrawled}
                        className="px-3 py-1.5 bg-slate-100 hover:bg-slate-200 text-slate-700 text-xs rounded-lg transition-colors font-medium border border-slate-200"
                      >
                        {selectedCrawledUrls.size === crawledGroups.length ? 'Bỏ chọn hết' : 'Chọn hết'}
                      </button>
                      <button 
                        onClick={handleImportSelected}
                        disabled={selectedCrawledUrls.size === 0}
                        className="px-3 py-1.5 bg-blue-600 hover:bg-blue-500 text-white font-bold text-xs rounded-lg transition-colors disabled:opacity-50 flex items-center gap-1 shadow-sm"
                      >
                        <Plus size={14} />
                        <span>Nhập {selectedCrawledUrls.size} nhóm vào target</span>
                      </button>
                      <button 
                        onClick={() => handleRunSearchJoin(Array.from(selectedCrawledUrls))}
                        disabled={selectedCrawledUrls.size === 0 || isSearching}
                        className="px-3 py-1.5 bg-blue-600 hover:bg-blue-500 text-white font-bold text-xs rounded-lg transition-colors disabled:opacity-50 flex items-center gap-1 shadow-sm"
                      >
                        {isSearching ? <RefreshCw className="animate-spin" size={12} /> : <Plus size={12} />}
                        <span>Tham gia {selectedCrawledUrls.size} nhóm đã chọn</span>
                      </button>
                    </div>
                  </div>

                  <div className="max-h-80 overflow-y-auto border border-slate-200 rounded-xl">
                    <table className="w-full text-left border-collapse text-xs">
                      <thead>
                        <tr className="bg-slate-50 border-b border-slate-200 text-slate-500 font-semibold">
                          <th className="p-2.5 w-10 text-center">Chọn</th>
                          <th className="p-2.5">Tên Group</th>
                          <th className="p-2.5 w-24">Thành viên</th>
                          <th className="p-2.5 w-28">Bài viết/ngày</th>
                          <th className="p-2.5">Link Group</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-slate-100">
                        {crawledGroups.map((g, idx) => (
                          <tr key={idx} className="hover:bg-slate-50 transition-colors">
                            <td className="p-2.5 text-center">
                              <input 
                                type="checkbox" 
                                checked={selectedCrawledUrls.has(g.url)}
                                onChange={() => handleSelectCrawled(g.url)}
                                className="w-4 h-4 accent-cyan-500 rounded border-slate-300 bg-white"
                              />
                            </td>
                            <td className="p-2.5 font-semibold text-slate-700">{g.name}</td>
                            <td className="p-2.5 text-slate-600 font-medium">{g.members || 'Không rõ'}</td>
                            <td className="p-2.5 text-slate-600 font-medium">{g.posts || 'Không rõ'}</td>
                            <td className="p-2.5 text-slate-500 font-mono">
                              <a href={g.url} target="_blank" rel="noreferrer" className="hover:underline text-cyan-600">
                                {g.url}
                              </a>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}

              {/* Logs Card */}
              {fbSubTab === 'campaign' && (
              <div className="bg-white p-6 rounded-2xl border border-slate-200 shadow-sm space-y-4">
                <div className="flex justify-between items-center">
                  <h2 className="text-xl font-bold flex items-center gap-2 text-slate-800">
                    <Activity size={20} className="text-green-600" />
                    Nhật ký Chiến dịch (Logs)
                  </h2>
                  <div className="flex items-center gap-2">
                    <button 
                      onClick={handleStopTasks}
                      disabled={isStopping}
                      className="px-3 py-1.5 bg-red-50 text-red-600 hover:bg-red-100 disabled:opacity-50 font-bold rounded-xl text-xs transition-all border border-red-200 shadow-sm flex items-center gap-1.5"
                      title="Dừng khẩn cấp tất cả tác vụ đang chạy"
                    >
                      <span className="w-2 h-2 rounded-full bg-red-600 animate-pulse"></span>
                      <span>Dừng tác vụ</span>
                    </button>
                    <button 
                      onClick={fetchLogs}
                      className="p-2 hover:bg-slate-100 rounded-lg text-slate-500 hover:text-slate-800 transition-colors border border-slate-200"
                      title="Tải lại log"
                    >
                      <RefreshCw size={16} />
                    </button>
                  </div>
                </div>
                <div className="bg-slate-900 p-4 rounded-xl border border-slate-950 h-64 overflow-y-auto font-mono text-xs text-green-400 space-y-1">
                  {logs ? logs.split('\n').map((line, idx) => (
                    <div key={idx}>{line}</div>
                  )) : 'Đang tải nhật ký...'}
                </div>
              </div>
              )}

            </div>

            {/* Right Side: Group List Selector & Editor (4 cols) */}
            <div className={`${fbSubTab === 'content' ? 'lg:col-span-12' : 'lg:col-span-4'} space-y-6`}>
              
              {/* Group Selector List */}
              {fbSubTab === 'group' && (
              <div className="bg-white p-6 rounded-2xl border border-slate-200 shadow-sm flex flex-col max-h-[30rem] space-y-3">
                <div className="flex justify-between items-center border-b border-slate-100 pb-2">
                  <h2 className="text-sm font-bold text-slate-800">
                    Chọn Group Target ({selectedTargetGroups.size}/{targetGroupsList.length})
                  </h2>
                  <button 
                    onClick={handleToggleAllTargetGroups}
                    className="text-xs font-semibold text-cyan-600 hover:text-cyan-500 hover:underline"
                  >
                    {selectedTargetGroups.size === targetGroupsList.length ? "Bỏ chọn hết" : "Chọn tất cả"}
                  </button>
                </div>
                <div className="flex-1 overflow-y-auto space-y-2 pr-1 text-xs">
                  {targetGroupsList.length === 0 ? (
                    <p className="text-slate-400 italic p-3 text-center">Chưa có link nhóm nào. Hãy crawl hoặc thêm nhóm ở dưới.</p>
                  ) : (
                    targetGroupsList.map((url, idx) => (
                      <label 
                        key={idx} 
                        className={`flex items-start gap-2.5 p-2.5 rounded-lg border cursor-pointer transition-colors ${selectedTargetGroups.has(url) ? 'bg-blue-50/50 border-blue-300' : 'bg-slate-50 border-slate-200 hover:border-slate-300'}`}
                      >
                        <input 
                          type="checkbox" 
                          checked={selectedTargetGroups.has(url)}
                          onChange={() => handleToggleTargetGroup(url)}
                          className="w-4 h-4 mt-0.5 accent-blue-600 rounded border-slate-300 bg-white"
                        />
                        <span className="font-mono break-all text-slate-600 font-medium hover:text-slate-900">{url}</span>
                      </label>
                    ))
                  )}
                </div>
              </div>
              )}

              {/* Group Links List Editor */}
              {(fbSubTab === 'group' || fbSubTab === 'campaign') && (
              <div className="bg-white p-6 rounded-2xl border border-slate-200 shadow-sm flex flex-col space-y-3">
                <div className="flex justify-between items-center">
                  <h2 className="text-sm font-bold text-slate-850 flex items-center gap-1">
                    <Settings size={16} className="text-cyan-600" />
                    Chỉnh Sửa File Link Nhóm
                  </h2>
                  <button 
                    onClick={fetchGroups}
                    className="p-1 hover:bg-slate-100 rounded text-slate-500 transition-colors border border-slate-200"
                  >
                    <RefreshCw size={12} />
                  </button>
                </div>
                <textarea 
                  value={groupsText}
                  onChange={(e) => setGroupsText(e.target.value)}
                  className="w-full p-3 bg-white border border-slate-200 rounded-xl focus:border-cyan-500 focus:outline-none font-mono text-[10px] text-slate-600 resize-none h-48 shadow-inner"
                  placeholder="https://www.facebook.com/groups/vieclamtayninh/&#10;https://www.facebook.com/groups/tuyendungtayninh/"
                />
                <button 
                  onClick={handleSaveGroups}
                  className="w-full py-2.5 bg-slate-800 hover:bg-slate-900 text-white font-semibold text-xs rounded-xl transition-colors shadow-sm"
                >
                  Lưu File Nhóm (target_groups.txt)
                </button>
              </div>
              )}

              {/* Library File list card */}
              {fbSubTab === 'content' && (
              <>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                  {/* Column 1: Kho bài viết (.txt) */}
                  <div className="bg-white p-6 rounded-2xl border border-slate-200 shadow-sm space-y-4">
                    <div className="flex justify-between items-center border-b border-slate-100 pb-2">
                      <h2 className="text-sm font-bold text-slate-800 flex items-center gap-1.5">
                        <FileText size={16} className="text-cyan-600" />
                        Kho Bài Viết AI (.txt)
                      </h2>
                      <button 
                        onClick={fetchLibrary}
                        className="p-1 hover:bg-slate-100 rounded text-slate-500 transition-colors border border-slate-200"
                      >
                        <RefreshCw size={12} />
                      </button>
                    </div>
                    <div className="max-h-72 overflow-y-auto space-y-1.5 pr-1 text-xs">
                      {libraryContents.length === 0 ? (
                        <p className="text-slate-400 italic">Trống</p>
                      ) : (
                        libraryContents.map((c, idx) => (
                          <div 
                            key={idx} 
                            onClick={() => setSelectedContentFile(c.filename)}
                            className={`p-3 rounded-xl border cursor-pointer transition-all ${selectedContentFile === c.filename ? 'bg-blue-50/50 border-blue-300 text-blue-800 font-semibold shadow-sm' : 'bg-slate-50 border-slate-100 hover:bg-slate-100 hover:border-slate-200'}`}
                          >
                            <p className="font-semibold truncate text-[13px]">{c.filename}</p>
                            <p className="text-slate-500 truncate text-[11px] mt-1">{c.preview}</p>
                          </div>
                        ))
                      )}
                    </div>
                  </div>

                  {/* Column 2: Kho hình ảnh (.jpg) */}
                  <div className="bg-white p-6 rounded-2xl border border-slate-200 shadow-sm space-y-4">
                    <div className="flex justify-between items-center border-b border-slate-100 pb-2">
                      <h2 className="text-sm font-bold text-slate-800 flex items-center gap-1.5">
                        <ImageIcon size={16} className="text-cyan-600" />
                        Kho Hình Ảnh AI (.jpg / .png)
                      </h2>
                      <div className="flex items-center gap-2">
                        <label className="cursor-pointer text-[10px] bg-blue-50 text-blue-600 hover:bg-blue-100 border border-blue-200 px-2 py-1 rounded font-semibold transition-colors">
                          📤 Tải ảnh lên
                          <input 
                            type="file" 
                            accept="image/*" 
                            className="hidden" 
                            onChange={handleImageUpload} 
                          />
                        </label>
                        <button 
                          onClick={fetchLibrary}
                          className="p-1 hover:bg-slate-100 rounded text-slate-500 transition-colors border border-slate-200"
                        >
                          <RefreshCw size={12} />
                        </button>
                      </div>
                    </div>
                    <div className="max-h-72 overflow-y-auto space-y-1.5 pr-1 text-xs">
                      {libraryImages.length === 0 ? (
                        <p className="text-slate-400 italic">Trống</p>
                      ) : (
                        libraryImages.map((img, idx) => (
                          <div 
                            key={idx} 
                            onClick={() => setSelectedImageFile(img.filename)}
                            className={`p-3 rounded-xl border cursor-pointer transition-all ${selectedImageFile === img.filename ? 'bg-blue-50/50 border-blue-300 text-blue-800 font-semibold shadow-sm' : 'bg-slate-50 border-slate-100 hover:bg-slate-100'}`}
                          >
                            <p className="font-semibold truncate text-[13px]">{img.filename}</p>
                          </div>
                        ))
                      )}
                    </div>
                  </div>
                </div>

              {/* Preview Selected Items Card */}
              {(selectedContentFile || selectedImageFile) && (
                <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 animate-fade-in">
                  {/* Text Preview Column */}
                  {selectedContentFile ? (
                    <div className="bg-white p-6 rounded-2xl border border-slate-200 shadow-sm space-y-4 text-xs">
                      <div className="border-b border-slate-100 pb-2 flex justify-between items-center">
                        <h2 className="text-sm font-bold text-slate-800 flex items-center gap-1.5">
                          👁️ Xem Trước Bài Viết: {selectedContentFile}
                        </h2>
                        <div className="flex gap-2">
                          {isEditingContent ? (
                            <>
                              <button 
                                onClick={handleSaveEditedContent}
                                className="px-3 py-1.5 bg-green-600 hover:bg-green-500 text-white rounded-lg font-semibold transition-colors text-[10px] shadow-sm"
                              >
                                💾 Lưu
                              </button>
                              <button 
                                onClick={() => { setIsEditingContent(false); setEditingContentText(selectedContentText); }}
                                className="px-3 py-1.5 bg-slate-100 hover:bg-slate-200 text-slate-700 rounded-lg font-semibold transition-colors text-[10px] border border-slate-200"
                              >
                                Hủy
                              </button>
                            </>
                          ) : (
                            <button 
                              onClick={() => setIsEditingContent(true)}
                              className="px-3 py-1.5 bg-blue-600 hover:bg-blue-500 text-white rounded-lg font-semibold transition-colors text-xs"
                            >
                              ✏️ Sửa bài viết
                            </button>
                          )}
                          <button 
                            onClick={() => handleDeleteContent(selectedContentFile)}
                            className="px-3 py-1.5 bg-red-50 hover:bg-red-100 text-red-600 rounded-lg font-semibold transition-colors text-[10px] border border-red-200"
                          >
                            Xóa bài viết
                          </button>
                          <button 
                            onClick={() => setSelectedContentFile('')}
                            className="px-2.5 py-1.5 bg-slate-100 hover:bg-slate-200 rounded-lg text-[10px] text-slate-600 transition-colors border border-slate-200"
                          >
                            Đóng
                          </button>
                        </div>
                      </div>
                      
                      <div className="space-y-1.5">
                        {isEditingContent ? (
                          <textarea
                            value={editingContentText}
                            onChange={(e) => setEditingContentText(e.target.value)}
                            className="w-full p-4 bg-slate-50 border border-blue-600 rounded-xl focus:bg-white focus:outline-none transition-all text-slate-800 text-sm shadow-inner h-64 resize-y font-mono leading-relaxed"
                          />
                        ) : (
                          <div className="p-3.5 bg-slate-50 border border-slate-100 rounded-xl max-h-96 overflow-y-auto font-sans whitespace-pre-line text-slate-700 leading-relaxed shadow-inner">
                            {selectedContentText}
                          </div>
                        )}
                      </div>
                    </div>
                  ) : <div className="hidden lg:block"></div>}

                  {/* Image Preview Column */}
                  {selectedImageFile ? (
                    <div className="bg-white p-6 rounded-2xl border border-slate-200 shadow-sm space-y-4 text-xs">
                      <div className="border-b border-slate-100 pb-2 flex justify-between items-center">
                        <h2 className="text-sm font-bold text-slate-800 flex items-center gap-1.5">
                          👁️ Xem Trước Ảnh: {selectedImageFile}
                        </h2>
                        <div className="flex gap-2">
                          <button 
                            onClick={() => handleDeleteImage(selectedImageFile)}
                            className="px-3 py-1.5 bg-red-50 hover:bg-red-100 text-red-600 font-semibold rounded-lg transition-colors text-[10px] border border-red-200"
                          >
                            Xóa ảnh
                          </button>
                          <button 
                            onClick={() => setSelectedImageFile('')}
                            className="px-2.5 py-1.5 bg-slate-100 hover:bg-slate-200 rounded-lg text-[10px] text-slate-600 transition-colors border border-slate-200"
                          >
                            Đóng
                          </button>
                        </div>
                      </div>
                      
                      <div className="rounded-xl overflow-hidden border border-slate-100 p-2 flex justify-center bg-slate-50">
                        <img 
                          src={imageObjectURL || 'https://placehold.co/400x300?text=Đang+tải+ảnh...'} 
                          alt={selectedImageFile}
                          className="max-h-[30rem] object-contain rounded-lg shadow-sm"
                          onError={(e) => {
                            (e.target as HTMLImageElement).src = 'https://placehold.co/400x300?text=Lỗi+tải+ảnh';
                          }}
                        />
                      </div>
                    </div>
                  ) : <div className="hidden lg:block"></div>}
                </div>
              )}
              </>
              )}

            </div>

          </div>
        )}

        {activeTab === 'research' && (
          <div className="space-y-6 animate-fade-in">
            <div className="bg-white p-6 rounded-2xl shadow-sm border border-slate-200">
              <h2 className="text-xl font-bold mb-4">Nghiên Cứu Thị Trường</h2>
              <div className="flex gap-4 mb-6">
                <input 
                  type="text" 
                  value={researchQuery} 
                  onChange={e => setResearchQuery(e.target.value)} 
                  placeholder="Nhập từ khóa ngành hàng (vd: thiết kế nội thất)" 
                  className="flex-1 px-4 py-3 border border-slate-200 rounded-xl focus:border-blue-600"
                />
                <button 
                  onClick={handleRunResearch}
                  disabled={isResearching}
                  className="px-6 py-3 bg-blue-600 hover:bg-blue-500 text-white font-bold rounded-xl disabled:opacity-50"
                >
                  {isResearching ? 'Đang chạy...' : 'Bắt đầu Nghiên Cứu'}
                </button>
              </div>

              <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
                {['google', 'facebook', 'maps', 'tiktok'].map(src => (
                  <div key={src} className="flex flex-col p-3 border rounded-xl bg-slate-50">
                    <label className="flex items-center gap-2 cursor-pointer font-semibold capitalize mb-2">
                      <input 
                        type="checkbox" 
                        checked={researchSources.has(src)} 
                        onChange={(e) => {
                          const newSrc = new Set(researchSources);
                          if (e.target.checked) newSrc.add(src); else newSrc.delete(src);
                          setResearchSources(newSrc);
                        }}
                        className="w-4 h-4 accent-blue-600"
                      />
                      {src}
                    </label>
                    <div className="flex items-center justify-between text-sm">
                      <span className="text-slate-500">Giới hạn:</span>
                      <input 
                        type="number"
                        min="1" max="100"
                        value={researchLimits[src] || 10}
                        onChange={(e) => setResearchLimits({...researchLimits, [src]: parseInt(e.target.value) || 10})}
                        className="w-16 px-2 py-1 border rounded text-right"
                      />
                    </div>
                  </div>
                ))}
              </div>
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
              <div className="lg:col-span-1 bg-white p-6 rounded-2xl shadow-sm border border-slate-200">
                <div className="flex justify-between items-center mb-4">
                  <h3 className="font-bold">Lịch sử Nghiên Cứu</h3>
                  <button onClick={fetchResearchHistory} className="text-blue-600"><RefreshCw size={18} /></button>
                </div>
                <div className="space-y-3 max-h-96 overflow-y-auto">
                  {researchHistory.map((item, idx) => (
                    <div key={idx} className="p-3 border rounded-xl hover:border-blue-300 bg-slate-50 text-sm flex justify-between items-center">
                      <div className="cursor-pointer flex-1" onClick={() => viewResearchFile(item.filename)}>
                        <div className="font-semibold text-blue-700">{item.query}</div>
                        <div className="text-xs text-slate-500">{new Date(item.created_at * 1000).toLocaleString()} • {item.result_count} kết quả</div>
                      </div>
                      <button onClick={() => deleteResearchFile(item.filename)} className="text-red-500 p-2 hover:bg-red-50 rounded-lg ml-2">Xóa</button>
                    </div>
                  ))}
                  {researchHistory.length === 0 && <p className="text-slate-500 text-sm">Chưa có dữ liệu</p>}
                </div>
              </div>

              <div className="lg:col-span-2 bg-white p-6 rounded-2xl shadow-sm border border-slate-200 overflow-x-auto">
                <h3 className="font-bold mb-4">Chi tiết Kết Quả {researchResults?.query ? `"${researchResults.query}"` : ''}</h3>
                {researchResults ? (
                  <table className="w-full text-left text-sm border-collapse">
                    <thead>
                      <tr className="bg-slate-100 border-b">
                        <th className="p-3 font-semibold text-slate-700">Tên/Tiêu đề</th>
                        <th className="p-3 font-semibold text-slate-700">Nền tảng</th>
                        <th className="p-3 font-semibold text-slate-700">Số Điện Thoại</th>
                        <th className="p-3 font-semibold text-slate-700">Liên kết</th>
                      </tr>
                    </thead>
                    <tbody>
                      {researchResults.results?.map((res: any, i: number) => (
                        <tr key={i} className="border-b hover:bg-slate-50">
                          <td className="p-3 font-medium max-w-[200px] truncate" title={res.title}>{res.title}</td>
                          <td className="p-3">
                            <span className="px-2 py-1 bg-blue-100 text-blue-800 rounded-full text-xs">{res.platform}</span>
                          </td>
                          <td className="p-3 font-mono text-green-600">{res.phone_direct || res.phone || '-'}</td>
                          <td className="p-3">
                            <a href={res.link} target="_blank" className="text-blue-600 hover:underline flex items-center gap-1">
                              Link <Globe size={14} />
                            </a>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                ) : (
                  <div className="text-center text-slate-500 py-10">Chọn một tệp từ lịch sử để xem chi tiết</div>
                )}
              </div>
            </div>
          </div>
        )}

      </div>
    </div>
  );
}

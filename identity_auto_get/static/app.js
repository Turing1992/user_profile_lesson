// 身份自动识别系统前端脚本

const API_BASE_URL = '/api';

// 默认提示词
const DEFAULT_PROMPT = `我想让你扮演网约车身份判断专家，我会给你输入一个账号的发帖的贴文，你帮我从文章中判断出他的身份
判断要求为：1，如果是广告则不做判断
2，如果是描述他人跑网约车的不算
3，如果贴文是新闻类型或者小说，短剧，则不做判断
4，注意区分乘坐网约车的和跑网约车的，如果是乘坐网约车的人怎不做判断
5，优先判断称自己是跑网约车的，跑滴滴的发文，不要一看到网约车就下结论
6，一定是描述发帖人自己跑网约车，只要出现名字，第三人称，引号中的我是xxx，都不算
7，出现"我跑网约车XXXX"这类表达要注意是否是小说
8，文本长度超过200字都不是网约车司机

5，输出格式为：
    {
    "identity":"平台配送与运输从业者",
    "identity2":"网约车司机",
    "log":"判断原因"
    }

请只返回判断的分类名称，信息如下：`;

// DOM 元素
const taskForm = document.getElementById('taskForm');
const loadingSpinner = document.querySelector('.loading-spinner');
const tasksContainer = document.getElementById('tasksContainer');
const refreshButton = document.getElementById('refreshTasks');
const useDefaultPromptButton = document.getElementById('useDefaultPrompt');
const toast = new bootstrap.Toast(document.getElementById('toast'));

// 初始化
document.addEventListener('DOMContentLoaded', function() {
    loadTasks();
    
    // 绑定事件
    taskForm.addEventListener('submit', handleTaskSubmit);
    refreshButton.addEventListener('click', loadTasks);
    useDefaultPromptButton.addEventListener('click', useDefaultPrompt);
});

// 显示通知
function showToast(message, type = 'info') {
    const toastBody = document.getElementById('toastBody');
    const toastHeader = document.querySelector('.toast-header i');
    
    toastBody.textContent = message;
    
    // 更新图标和样式
    toastHeader.className = `bi me-2 ${getToastIcon(type)}`;
    
    toast.show();
}

function getToastIcon(type) {
    switch(type) {
        case 'success': return 'bi-check-circle text-success';
        case 'error': return 'bi-exclamation-triangle text-danger';
        case 'warning': return 'bi-exclamation-triangle text-warning';
        default: return 'bi-info-circle text-info';
    }
}

// 使用默认提示词
function useDefaultPrompt() {
    document.getElementById('promptText').value = DEFAULT_PROMPT;
    showToast('已填入默认提示词', 'success');
}

// 处理任务提交
async function handleTaskSubmit(event) {
    event.preventDefault();
    
    const formData = new FormData(taskForm);
    const data = {
        match_keywords: document.getElementById('matchKeywords').value,
        identity_name: document.getElementById('identityName').value,
        creator: document.getElementById('creator').value,
        prompt_text: document.getElementById('promptText').value || undefined
    };
    
    // 显示加载状态
    loadingSpinner.style.display = 'block';
    taskForm.querySelector('button[type="submit"]').disabled = true;
    
    try {
        const response = await fetch(`${API_BASE_URL}/tasks`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify(data)
        });
        
        const result = await response.json();
        
        if (result.success) {
            showToast('任务创建成功，正在后台处理数据...', 'success');
            taskForm.reset();
            loadTasks(); // 刷新任务列表
        } else {
            showToast(`创建失败: ${result.message}`, 'error');
        }
    } catch (error) {
        console.error('Error creating task:', error);
        showToast('网络错误，请稍后重试', 'error');
    } finally {
        // 隐藏加载状态
        loadingSpinner.style.display = 'none';
        taskForm.querySelector('button[type="submit"]').disabled = false;
    }
}

// 加载任务列表
async function loadTasks() {
    try {
        const response = await fetch(`${API_BASE_URL}/tasks`);
        const result = await response.json();
        
        if (result.success) {
            renderTasks(result.data);
        } else {
            tasksContainer.innerHTML = `
                <div class="alert alert-danger">
                    <i class="bi bi-exclamation-triangle"></i> 
                    加载任务列表失败: ${result.message}
                </div>
            `;
        }
    } catch (error) {
        console.error('Error loading tasks:', error);
        tasksContainer.innerHTML = `
            <div class="alert alert-danger">
                <i class="bi bi-wifi-off"></i> 
                网络错误，无法加载任务列表
            </div>
        `;
    }
}

// 渲染任务列表
function renderTasks(tasks) {
    if (tasks.length === 0) {
        tasksContainer.innerHTML = `
            <div class="text-center py-5 text-muted">
                <i class="bi bi-inbox" style="font-size: 3rem;"></i>
                <div class="mt-3">暂无任务</div>
            </div>
        `;
        return;
    }
    
    const tasksHtml = tasks.map(task => `
        <div class="col-md-6 col-lg-4 mb-4">
            <div class="card task-card h-100">
                <div class="card-header d-flex justify-content-between align-items-center">
                    <h6 class="mb-0">${escapeHtml(task.identity_name)}</h6>
                    ${getStatusBadge(task.task_status)}
                </div>
                <div class="card-body">
                    <p class="card-text">
                        <strong>关键词:</strong> ${escapeHtml(task.match_keywords)}<br>
                        <strong>创建人:</strong> ${escapeHtml(task.creator)}<br>
                        <strong>创建时间:</strong> ${task.created_time}
                    </p>
                    
                    <div class="prompt-preview">
                        <strong>提示词预览:</strong><br>
                        ${escapeHtml(task.prompt_text.substring(0, 100))}...
                    </div>
                </div>
                <div class="card-footer">
                    <div class="d-flex justify-content-between">
                        <button class="btn btn-sm btn-outline-info" onclick="viewTask(${task.id})">
                            <i class="bi bi-eye"></i> 查看详情
                        </button>
                        ${task.task_status === '创建完成' && task.result_file_path ? 
                            `<button class="btn btn-sm btn-success" onclick="downloadResult(${task.id})">
                                <i class="bi bi-download"></i> 下载结果
                            </button>` : 
                            `<button class="btn btn-sm btn-secondary" disabled>
                                <i class="bi bi-hourglass-split"></i> 处理中
                            </button>`
                        }
                    </div>
                </div>
            </div>
        </div>
    `).join('');
    
    tasksContainer.innerHTML = `<div class="row">${tasksHtml}</div>`;
}

// 获取状态徽章
function getStatusBadge(status) {
    const badges = {
        '创建中': '<span class="badge bg-warning status-badge">创建中</span>',
        '测试中': '<span class="badge bg-info status-badge">测试中</span>',
        '创建完成': '<span class="badge bg-success status-badge">创建完成</span>'
    };
    return badges[status] || '<span class="badge bg-secondary status-badge">未知</span>';
}

// 查看任务详情
async function viewTask(taskId) {
    try {
        const response = await fetch(`${API_BASE_URL}/tasks/${taskId}`);
        const result = await response.json();
        
        if (result.success) {
            const task = result.data;
            
            // 创建模态框显示详情
            const modalHtml = `
                <div class="modal fade" id="taskDetailModal" tabindex="-1">
                    <div class="modal-dialog modal-lg">
                        <div class="modal-content">
                            <div class="modal-header">
                                <h5 class="modal-title">任务详情 - ${escapeHtml(task.identity_name)}</h5>
                                <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
                            </div>
                            <div class="modal-body">
                                <div class="row">
                                    <div class="col-md-6">
                                        <p><strong>任务ID:</strong> ${task.id}</p>
                                        <p><strong>身份名称:</strong> ${escapeHtml(task.identity_name)}</p>
                                        <p><strong>匹配关键词:</strong> ${escapeHtml(task.match_keywords)}</p>
                                        <p><strong>创建人:</strong> ${escapeHtml(task.creator)}</p>
                                    </div>
                                    <div class="col-md-6">
                                        <p><strong>任务状态:</strong> ${getStatusBadge(task.task_status)}</p>
                                        <p><strong>创建时间:</strong> ${task.created_time}</p>
                                        <p><strong>更新时间:</strong> ${task.updated_time}</p>
                                    </div>
                                </div>
                                
                                <div class="mt-3">
                                    <strong>提示词:</strong>
                                    <pre class="bg-light p-3 mt-2" style="max-height: 300px; overflow-y: auto;">${escapeHtml(task.prompt_text)}</pre>
                                </div>
                                
                                ${task.result_file_path ? 
                                    `<div class="mt-3">
                                        <strong>结果文件:</strong> ${escapeHtml(task.result_file_path)}
                                    </div>` : ''
                                }
                            </div>
                            <div class="modal-footer">
                                ${task.task_status === '创建完成' && task.result_file_path ? 
                                    `<button class="btn btn-success" onclick="downloadResult(${task.id})">
                                        <i class="bi bi-download"></i> 下载结果
                                    </button>` : ''
                                }
                                <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">关闭</button>
                            </div>
                        </div>
                    </div>
                </div>
            `;
            
            // 移除旧的模态框
            const oldModal = document.getElementById('taskDetailModal');
            if (oldModal) {
                oldModal.remove();
            }
            
            // 添加新的模态框
            document.body.insertAdjacentHTML('beforeend', modalHtml);
            const modal = new bootstrap.Modal(document.getElementById('taskDetailModal'));
            modal.show();
            
        } else {
            showToast(`获取任务详情失败: ${result.message}`, 'error');
        }
    } catch (error) {
        console.error('Error viewing task:', error);
        showToast('网络错误，无法获取任务详情', 'error');
    }
}

// 下载结果文件
function downloadResult(taskId) {
    const downloadUrl = `${API_BASE_URL}/tasks/${taskId}/download`;
    
    // 创建隐藏的下载链接
    const link = document.createElement('a');
    link.href = downloadUrl;
    link.download = `identity_analysis_task_${taskId}.xlsx`;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    
    showToast('开始下载结果文件...', 'success');
}

// HTML 转义函数
function escapeHtml(text) {
    const map = {
        '&': '&amp;',
        '<': '&lt;',
        '>': '&gt;',
        '"': '&quot;',
        "'": '&#039;'
    };
    return text.replace(/[&<>"']/g, function(m) { return map[m]; });
}

// 定期刷新任务状态
setInterval(() => {
    loadTasks();
}, 30000); // 每30秒刷新一次
# Phase 2: 图像生成模式

本文为设计草稿，文档中的所有内容：命名、设计等均未确定，可能修改。本文档确认没有问题后才开始写正式设计文档。

## 目标

- 静态角色立绘 + 静态背景图片
- 为保持可拓展性：程序设计尽量兼容任意类型的“媒体数据”，本文主要以上述两类图像数据为例
- 图像模式与文本模式不走同一个 UI 叙事界面，文本模式不丢弃
- 展示模式为传统视觉小说游戏模式（Galgame、《明日方舟》等）

## 核心模式

### 媒体数据库

- 当前媒体数据主要形式为图像，包括“背景图片”，“角色立绘”的核心两大类，未来可拓展，这是两个完全不同的数据类
- 所有媒体数据具体的文件存储结构不重要，重要的是路径索引被记录

**角色立绘**：
- 每个角色立绘图像类包含：ID + name + 描述 + 图片路径 + 使用计数，仅作为建议，可修改
- 保持可分类性，类似于 variables 的命名空间，为以后拓展“小明.微笑”这种形式奠定基础

**背景图像**：
- 与“角色立绘”要求基本一致，但两者属于不同内容类型，具体成员完全可以不一样，图像格式也大概率不同

**全局库和游戏库**：
- 媒体数据库需要分为游戏库与全局库，游戏库作用域为一局游戏，全局库作用域为 Storyloom 程序
- 库中都包含若干基本的媒体数据类型（角色立绘、背景图像等）
- 游戏库为全局库的子集，可以直接引用全局的数据；而每次游戏库新“生成”的媒体数据都需要加入全局库
- 相同媒体数据在游戏库与全局库可能有不同“名称”——不影响，重要的是 ID 或者路径唯一
- 为了保证全局库不过度膨胀，需要有清理机制，可以内部记录使用次数，当总量过多时清理使用次数少的媒体数据
- 存档时需要存储当前的游戏库状态，如果读档时数据破坏，交给专门的错误处理机制

### 选择 & 生成（两者后文统称“制作”）

- AI 根据媒体数据的基本类型、名称、描述等，基于现有的库（游戏库优先，全局次之）自行决定制作方式（仅根据名称、描述进行匹配）
- 如果名称等信息与现有库内容完全匹配，也可通过程序直接“选择”，跳过 API 请求
- 选择：AI 选择一个已经存在的媒体数据类，返回ID或路径等唯一性信息
- 生成：AI 自行生成图像，后台执行，生成完毕后添加到游戏库和全局库，返回这个新增图像的信息
- 当没有配置图像生成 API 时，强制走选择模式

## AI 与提示词

### AI 定位与分类

**A.共创聊天 LLM**：
- 行为与之前一致，与用户自由交流，提供构建素材

**B.故事设定、大纲生成 LLM**：
- 行为与之前一致，生成内容基本不变

**C.游戏素材预构建 AI**（新增）：
- 基于生成设定中的“地点”“角色”，**制作**游戏的初始媒体数据，直接加入库中
- 不要求一一对应，可以制作更多，例如地点为“学校”，可以制作“学校.教室”、“学校.操场”等背景图像
- 完全支持“选择”模式，即直接把全局库的数据放入到本局的游戏库中，类似于流程 `E`

**D.叙事阶段 LLM**（修改）：
- 作为游戏故事的“导演”，依然只负责纯文本 XML 生成
- 在原有的基础上添加一些标签元素：场景/地点标签、角色立绘标签，“导演”负责进行编排
- LLM 自行判断是否需要添加“描述”（环境/外貌），例如设定中的地点就不需要，新出现的角色就需要
- 场景/地点:
  - 必须展示，只能切换不能置空，“Continue from”或其他部分说明上轮此处的场景，方便 LLM 承接
  - 变化频率较低，完全可以新设置一个元素 `<scene name="xxx">...description...</scene>`
  - 若不需要描述，可以自闭合 `<scene name="xxx"/>` 或者就不写描述
  - 此标签负责场景切换，UI 侧处理时，需要和 `<seg>` 一样占用专门的等待时间
- 角色立绘：
  - 变化频率极高，若不需要描述，建议作为 `<seg>` 的子元素，例如 `<seg character="xxx">........</seg>`
  - 若需要描述，添加标签：`<character name="xxx"/>...description...</character>`，然后再正常使用，此标签不切换立绘
  - 立绘也可以不展示，此时保留原样：`<seg>......</seg>`，表示此处不需要展示角色立绘
- 当遇到 scene、character 等标签时，触发“制作”任务（告知 AI 名称、描述），获得图像结果，并最终与 `SCENE`、`SEG`、`CHARACTER` 事件进行对应。`CHARACTER` 只负责提前制作图像并直接入库，不需要向 UI 发送

**E.媒体数据实时制作 AI**（新增）：

- 当遇到 scene、character 等元素时触发“制作”任务，如果能够精准匹配名称，由程序直接“选择”，跳过 API 请求
- 本质上包括两次 API 的调用：1. LLM 快速判断 2. 可能触发的图像生成 AI 调用
- LLM 快速调用
    - （构想）LLM 快速判断也许不需要“思考”，可以尝试通过在程序端针对模型添加特定 extra_body 关闭“思考”，加快响应速度
    - LLM 接收素材的名称和描述，图像库数据的名称和描述，返回判断结果（“选择”-返回其图像唯一性信息）
- 图像生成 AI 调用
    - 若 LLM 返回“生成”，由程序负责调用图像生成 API ，获得/下载图像结果，并加入到图像库中
    - 返回：图像的唯一性信息，如路径，ID 等

**F.冒险日志生成 LLM**
- 行为与之前一致

### 提示词

**游戏素材预构建 Prompt**
- 角色立绘、场景图片等用不同的提示词
- 对于每一个角色/场景，建议使用多线程执行构建流程，减少生成用时
- 传入角色/场景的名称、描述，以及完整的全局库（此时游戏库为空），调用 LLM 快速判断
- 这个阶段传入全局库信息时可以不说明“名称”，防止仅仅因为名称不同被 LLM 丢弃
- 若判断结果为需要“生成”，传入详细描述和“范例图像”，调用图像生成 API 进行生成
- 说明同一内容要求可以生成多个不同方向的图片，大约1-3个，例如角色：笑/平静/愤怒，学校：教师/操场/图书馆

**叙事阶段提示词 Prompt**
- 主要修改在前缀部分
  - 简单添加图像模式说明，让其理解自己的任务与设置各种标签的原因
  - 添加 `<scene>`/ `<character>` / `<seg character>` 标签格式说明和要求
  - 彻底更新或重构示例，保持示例 1 侧重交互自由度，示例 2 侧重剧情大纲关联性。

**媒体数据实时制作 Prompt**
- 每次“制作”任务触发时，自身维持一个线程，API 调用流程在程序直接匹配失败后进入
- 角色立绘、场景图片等用不同的提示词
- 传入角色/场景的名称、描述，以及游戏库、全局库（按频率截取20个左右）图像的名称、描述，调用 LLM （无“思考”）快速判断
- 若判断结果为需要“生成”，传入详细描述和近三张同类型图像（Event Generator存储，不足时传游戏库内容），调用 API 进行生成
- 保证流程用时短为核心，一次仅能选择或生成一张图像

## 流程解析

### 共创流程
- 额外添加：游戏素材构建流程
- 将一些关键素材加入到素材库

### 叙事流程

**Main LLM(Director)**
produce: XML tokens
to: Token Buffer

-- tokens -->
**Token Buffer(Queue1)**
store: tokens
to: if (consume): Line Generator

-- tokens -->
**Line Generator**
produce: 
- Line: index(003), type(seg), info
- Requirement: type(scene), name, description("")
to:
- Lines Buffer (Line)
- if (type=scene or character or seg(has_character)): Task Generator(Requirement)

route1: 

    -- Line -->
    **Lines Buffer(Queue2)**
    store: Line
    to: if (consume): Event Generator

route2: 

    -- Requirement -->
    **Task Generator**
    process: Produce tasks that get media data result
    produce: Task: type(character), branch(main), buffer, daemon_thread(opt), completed(false), result(scene_img)
    to: Tasks Buffer

    -- Task -->
    **Tasks Buffer(Queue3)**
    store: Task
    to: if (GET_TASK): Event Generator

-- Line -->/
-- Task -->/
-- UI_feedback -->
**Event Generator**
process: 
- Stream-parse Line to Event
- Correspond Event
    - if (CHOICE_END)
        - if (UI_feedback): get_result(UI_feedback)
        - else: wait
    - if (SCENE or CHARACTER or SEG(has_character))
        - do GET_TASK while (Task.branch != main/current_branch)
        - if (Task.completed): get_result(Task.result)
        - else: wait
- Apply: SET/CHECKPOINT/BRIDGE...
produce: Event
to:
- if (SET or BRIDGE or CHARACTER...): null
- else: UI Buffer

### 关键说明

时序模型：
> LLM 生成 >= 程序流式解析/媒体数据制作 >= UI 展示

LLM 生成：
- 使用了一个简单的小缓冲队列 Token Buffer ，和一个行生成器 Line Generator
- Line Generator 时序几乎和 LLM 生成完全一致，基本从不存在时间差异
- 效果是将 LLM 生成流：从产生 token 的流程转换为生成 Line 的流程，好处是生成的第一时间就可以判断类型，类似于“预处理”
- 主要就是需要检测“制作”媒体数据的行标签，并交给新增的后续流程进行提前处理

媒体数据制作：
- 包含一个任务生成器 Task Generator 和一个任务存储队列 Tasks Buffer
- Task Generator 本质服务于 Line Generator，且 Requirement 类型为抽象设计—— Line Generator 会产生两种类型并放入不同队列
- 对于每个媒体数据制作需求，创建一个后台线程任务 Task ，相对独立、互不干扰，完成顺序不重要，保证队列顺序稳定即可
- 队列需要持续监听 Event Generator 的消费请求，若发起请求：不管队首 Task 是否完成直接出队

程序流式解析：
- 事件生成器 Event Generator（内含解析器），接收 Lines Buffer, Tasks Buffer, UI 三路输入
- 原来的解析器已经被拆分，Event Generator 只需要完成从 Line 到 Event 的解析即可
- 触发选项事件时，需要等待用户反馈才能继续
- 触发媒体制作相关事件时，从队列消费 Task，不符合分支的 Task 关闭并丢弃，需要等待 Task 完成才能继续


## 实现方案

### 重构解析器（仍属于 Phase1）

- 设计 Line 类：包含行号，标签，内容信息等成员
- 基于原有队列设计，构建出两种线程安全队列：Token Buffer 和 Line Buffer
- 将解析器流程拆分为两个部分：Lines Generator 和 Event Generator ，中间用 Line Buffer 连接
- 前者负责初步处理：截取行，拆分行编号，分析标签类型，传输 Line 类
- 后者负责后续解析处理，对于不同类型标签采用不同解析方式

验证：重构后依然能够完整跑通 Phase1 流程

### 图像生成模块搭建和模式区分

- 设计专门的媒体数据存储目录
- 搭建基本的图像 API 调用模块，初步实现图像“生成”功能
- 为用户基本配置添加模式配置、图像 API 配置等功能
- UI 进行适配

验证：能够在本地目录中看到 AI 生成图像结果，且纯文本模式可稳定运行

### 添加场景、角色元素

- 重构叙事阶段 Prompt ，添加 scene, character 相关元素
- Event Generator 和 Line Generator 添加对于 scene, character 相关元素的解析
- 仅适配纯文本模式：Line Generator 仅判断其类型不处理；Event Generator 暂时对相关类型直接丢弃（带 character 的 seg 以简单 SEG 事件传输）

验证：在新提示词和返回设计下 UI 游玩纯文本模式依然稳定，不存在问题

### 构建基本媒体数据库管理架构

- 设计特定媒体数据类，目前包括：角色立绘、场景图像
- 搭建全局与游戏媒体数据库，实现特定类型的频率排序、完整展示（有无name）、全局截取展示、自动清理、错误处理等基础功能

验证：通过测试代码和图像（人工添加）验证数据库基础功能完整性

### 设计共创阶段图像“制作”流程

- 需要保留对纯文本模式的兼容性，提供不同进入渠道
- 验证无“思考”模式可行性，并设计无“思考”（可选，传参区分）的 LLM “选择”流程
- 设计**游戏素材预构建 Prompt**和并搭建完整的“制作”流程，初步填充游戏库与全局库内容
- 参照共创阶段设计，可初步搭建叙事阶段的图像“制作”流程框架，暂不设计 Prompt、不调用流程

验证：通过共创阶段能够在本地生成初始的媒体数据库，具备“选择”机制，且能够多线程同时生成

### 设计叙事阶段图像“制作”流程

- 参照共创阶段，设计**媒体数据实时制作 Prompt**
- 参照共创阶段，搭建完整的“制作”流程

验证：通过测试代码调用，能在本地查看到生成的图像数据，具备“选择”机制，且能够多线程同时生成

### 新增任务构建与任务缓冲

- 设计 Task 类，满足创建“制作”任务、后台线程独立执行等各种复杂要求
- 设计 Task Buffer 线程安全队列
- 为 Lines Generator 添加图像模式的类型检测和 Requirement 抽象创建
- 为 Lines Generator 添加 Task Generator 模块，并实现 Task 构建功能

验证：通过测试代码调用，Lines Generator 和 Task 能够正确处理其工作，填充任务队列，产生正确的数据库影响

### 事件生成器新增任务类型处理

- 为 Event Generator 设计基本的任务获取消费和等待逻辑
- 能向 UI 正常发送场景、角色相关事件
- UI 暂时不处理相关事件，带 character 的 SEG 以普通 SEG 形式处理

验证：图像模式可以在文本模式的 UI 效果下完整跑通，数据图像正常管理

### 设计图像模式的新 UI

- 为图像模式添加新的 UI 叙事界面

验证：Phase2 构想完全落地


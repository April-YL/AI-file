"""Program-level profiles for LLM ingest review.

Profiles define what "read correctly" looks like for each workpaper area.
The generic ingest review engine stays in ``ingest_review.py``; this module
keeps program-specific anchors and false-positive guardrails separate.
"""

PROGRAM_PROFILE_HINT = """固定资产 K1 底稿通常包含：
- 汇总页：程序目录、是否执行、不执行理由和注意事项。
- K.00 Lead Sheet：基础信息、TE/SAD/CRA/TT、预期分析、波动说明和调整汇总。
- K.01 Agree SL to GL：后推明细表、TB/FA list/利润表核对和 Notes。
- FA list：固定资产明细清单。
- K.02.1 新增测试程序包：新增清单、K.02.1 新增测试、K.02.1a 选样输出。
- K.02.2 处置测试程序包：处置清单、K.02.2 处置测试、K.02.2a 选样输出。
- K.03 折旧程序：K.03.1 SAP、K.03.2 折旧 TOD / by item、K.03.3 折旧政策复核。

请基于 sheet 名称、局部预览、表头字段和锚点判断是否存在读取层风险。
如果没有明确锚点，不要把非标准名称直接判为 suspicious。"""

SUMMARY_PROFILE_HINT = """汇总页通常用于列示固定资产 PSP 程序、程序页索引、是否执行、不执行原因和注意事项。

请特别注意：
- 强锚点包括“程序页”“是否执行”“不执行的原因”“注意事项”“PSP/Specific Performance”等。
- SWP 标准版式和 classic 四列简版都是合法版式；不得仅因列数或列位置不同判 suspicious。
- sheet 名称存在尾随空格或写作“汇总 ”时仍可能是有效汇总页，应结合内容锚点判断。
- “程序页”列不得与仅含“程序”的描述列混淆；“是否执行”列不得与“不执行的原因”混淆。
- 如果发现疑似漏读，只提出候选 sheet、候选行和锚点证据，不判断 PSP 是否完成。"""

LEAD_PROFILE_HINT = """K.00 Lead Sheet 通常包含六个区域：
1) 基础信息和重要性（客户名称、期末、分析日期、TE/SAD/PM、GAAP、币种）；
2) CRA / TT 风险阈值；
3) 预期分析；
4) 引导主表 / 波动判断表；
5) 异常波动说明；
6) 调整汇总表。

请特别注意：
- no_cra_te_volatility 是已知合法简版 Lead：无 CRA/TT 区且波动幅度金额取自 TE；不得仅因缺 CRA 区判 suspicious。
- Lead 调整汇总可能包含“本年度不涉及审计调整”、TE/SAD 说明或结论性文字，不应直接视为调整明细。
- 引导主表的“基于波动幅度判断/基于定性考虑判断”两列很重要，疑似漏读时只提示读取风险。
- 如果发现疑似漏读，只提出候选区域、行号和锚点证据，不评价预期或波动说明是否充分。"""

K01_PROFILE_HINT = """K.01 后推表通常包含六个物理区块：
1) 表1 BKD 主矩阵；
2) 变动 / TB / 差异区；
3) 表2 FA list 分类汇总；
4) 表3 表2 check with 表1；
5) 表4 折旧费用与利润表核对；
6) Notes / SAD / TE / 程序路由。

请特别注意：
- 表3 check、TB check、表4折旧核对是不同专题，Notes 不得混用。
- 仅有“变动金额”不等于可靠 TB check；可靠 TB check 通常需要 TB/试算表口径和“差异”标签同时出现。
- 表4折旧费用与利润表核对的差异不得被当作 TB 差异。
- hybrid / category_dual_period 是案例库常见合法版式，不得仅因不符合 SOP 标准矩阵而判 suspicious。
- 如果发现疑似漏读，只提出候选 sheet、候选行、锚点证据和建议动作，不计算金额、不判断是否超过 SAD。"""

K021_ADDITION_PROFILE_HINT = """K.02.1 新增测试通常是三表程序包：
1) 新增清单；
2) K.02.1 新增测试；
3) K.02.1a 新增选样输出。

请特别注意：
- 程序包执行路径可能是 full_expected、summary_waived 或 documented_limited；程序包不完整不必然等于程序未执行。
- K.02.1 标准模板右侧 SOP/易错点说明区可能包含“差异”“剩余总体”等文字，不得把说明区当作业务编制区。
- 新增清单金额列可能是“期末原值”或“新增原值”，不能机械要求固定列名。
- 新增方式/购置/外购、在建转入、企业合并、调拨、重分类等字段对总体识别很关键；疑似漏映射时只提示读取风险。
- K.02.1a 的样本池、TE、CRA、抽样方法、已选取样本是读取对象；不得判断金额、样本量或 TE/CRA 是否正确。"""

K022_DISPOSAL_PROFILE_HINT = """K.02.2 处置测试通常是三表程序包：
1) 处置清单；
2) K.02.2 处置测试；
3) K.02.2a 处置选样输出。

请特别注意：
- 汇总页已拒绝执行且理由指向处置金额低于阈值时，缺 K.02.2 / K.02.2a 可能是正常执行路径，不得机械判 suspicious。
- 处置测试总体通常关注出售+报废净值；“转入”“重分类”等其他减少不应简单等同于处置测试总体。
- 处置清单、减少清单、K.02.2b 处置/减少清单是常见命名变体；不得仅因名称非标准判漏读。
- K.02.2a 选样输出与 K.02.2 实测页的样本类型可能存在差异；读取层只提示候选位置，不判断样本匹配结论。
- 如果发现疑似漏读或错分，只提出候选 sheet、候选行、净值/处置方式/选样锚点证据，不计算金额。"""


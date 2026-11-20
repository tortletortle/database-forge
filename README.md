# 数据库自动生成算法

> 状态：Private 开发仓

## 当前完成度

- 记录进度：V0.2 已迁入、V0.3 实验原型完成；尚未证明普遍端到端加速
- **未经验收功能不得标记为已完成。**

## 目标 / 架构 / 运行方式

- [V0.3 最新实验原型](dbforge_v03/README.md)：自适应边际收益调度，23 项本地测试通过。
- [V0.3 实验记录](dbforge_v03/EXPERIMENT.md)：126 次合成数据构建对照。
- [V0.2 保留基线](dbforge_v02/README.md)：预算感知固定策略。

在对应版本目录执行 `python -m unittest -v`。

## 工程约定

1. 一项目一仓库 · 开发期 Private
2. 保留本地 Git 历史与 tags
3. 版本附测试报告与变更记录（docs/）

## 迁移

若本地已有完整历史：

```bash
cd <本地目录>
git remote add origin https://github.com/tortletortle/database-forge.git
git push -u origin --all
git push origin --tags
```

不要用骨架 force push 覆盖已有历史。

## V0.4 — evidence-reuse generation engine

- [Source and usage](dbforge_v04/README.md)
- [Experiment summary](dbforge_v04/EXPERIMENT.md): 30 unit tests and 108 verified synthetic-data builds; up to 1.201x median paired speedup in these cases. Earlier versions retained.

# RAG璇勬祴鑴氭湰浣跨敤鏁欑▼

## 1. 鐩殑

鏈洰褰曚笅鎻愪緵 3 涓揩閫熻瘎娴嬭剼鏈細

- `eval_recall.py`
  鐢ㄤ簬璇勪及 5 璺仈鍚堟绱㈢殑鍙洖琛ㄧ幇锛岀粺璁?`Top1 / Top3 / Top5`銆?
- `eval_precision.py`
  鐢ㄤ簬鍏堢敓鎴愭湁 RAG 鐨勫洖绛旓紝鍐嶅鍥炵瓟鍋氱簿纭巼璇勪及銆?
- `eval_hallucination.py`
  鐢ㄤ簬鐢熸垚鏃?RAG 鍥炵瓟锛屽苟涓庢湁 RAG 鍥炵瓟鍋氬够瑙夌巼瀵规瘮銆?

鍏叡閫昏緫鍦細

- `rag_eval_common.py`


## 2. 褰撳墠鎵ц绾︽潫

涓轰簡鎺у埗璧勬簮娑堣€椾笌 token 椋庨櫓锛屽綋鍓嶈剼鏈寜浠ヤ笅瑙勫垯鎵ц锛?

- 妫€绱㈤樁娈典笉骞惰銆?
- LLM 闃舵褰撳墠瀹炵幇涔熶笉骞惰銆?
- 鍥犳褰撳墠瀹炵幇澶╃劧婊¤冻鈥滄绱笉鑳藉苟琛岋紱LLM 骞惰鏈€澶?10 涓疄浣撯€濈殑瑕佹眰銆?

濡傛灉浠ュ悗瑕佹敼鎴愬苟琛岋細

- 妫€绱㈠苟琛屽害蹇呴』淇濇寔涓?`1`銆?
- LLM 骞惰搴︿笂闄愬繀椤诲皬浜庣瓑浜?`10`銆?


## 3. 寤鸿杩愯鐜

寤鸿浣跨敤 WSL 閲岀殑 Python 杩愯锛岃€屼笉鏄?Windows 鑷甫鐨?`python.exe` 鍒悕銆?

绀轰緥锛?

```bash
wsl
cd /mnt/e/AI/Learning-Platform/Lianjue_Backend
python3 --version
```

濡傛灉浣犵殑渚濊禆鍦?conda 鐜涓紝涔熷彲浠ュ厛婵€娲伙細

```bash
wsl
cd /mnt/e/AI/Learning-Platform/Lianjue_Backend
conda activate lianjue
python3 --version
```


## 4. 杈撳叆涓庤緭鍑?

榛樿杈撳叆娴嬭瘯鐢ㄤ緥鏂囦欢锛?

- `娴嬭瘯鐢ㄤ緥.md`

榛樿杈撳嚭鐩綍锛?

- `experiments/RAG/eval_outputs/`

甯歌杈撳嚭鏂囦欢锛?

- `recall_eval.json`
- `recall_eval.md`
- `precision_top1.json`
- `precision_top1.md`
- `precision_top3.json`
- `precision_top3.md`
- `precision_summary.md`
- `hallucination_eval.json`
- `hallucination_eval.md`


## 5. 鏍稿績鍙傛暟

涓変釜鑴氭湰閮芥敮鎸佷互涓嬫€濊矾锛?

- 鐢?`--phase` 鎷嗗垎鈥滅敓鎴愰樁娈碘€濆拰鈥渏udge 闃舵鈥濄€?
- 鐢?`--offset` + `--limit` 鎺у埗涓€娆″彧璺戜竴娈垫祴璇曠敤渚嬨€?
- 鐢?`--append` 鎶婅繖涓€娈电粨鏋滃苟鍏ュ凡鏈夋€荤粨鏋滄枃浠躲€?
- 鐢?`--batch-size 20` 鎺у埗姣忎竴鎵瑰鐞嗕笌钀界洏鐨勬潯鏁般€?

甯哥敤鍙傛暟璇存槑锛?

- `--graph-name`
  鍥捐氨鍚嶇О銆俙eval_recall.py` 鍜?`eval_precision.py` 蹇呭～銆?
- `--phase`
  鍙€夊€煎彇鍐充簬鑴氭湰锛?
  - `eval_recall.py`: `retrieve | judge | all`
  - `eval_precision.py`: `generate | judge | all`
  - `eval_hallucination.py`: `generate | judge | all`
- `--offset`
  浠庣鍑犳潯寮€濮嬪彇銆?
- `--limit`
  鏈鏈€澶氬彇澶氬皯鏉°€?
- `--append`
  灏嗘湰娆＄粨鏋滃悎骞惰繘宸叉湁缁撴灉鏂囦欢锛岃€屼笉鏄鐩栥€?
- `--batch-size`
  姣忔壒澶勭悊澶氬皯鏉°€傚缓璁繚鎸?`20`銆?


## 6. 鎺ㄨ崘宸ヤ綔娴?

寤鸿鎸?20 鏉′竴缁勫畬鏁存帹杩涖€?

鎬诲叡 50 鏉℃祴璇曠敤渚嬫椂锛屽彲鍒嗘垚 3 缁勶細

- 绗?1 缁勶細`offset=0 limit=20`
- 绗?2 缁勶細`offset=20 limit=20`
- 绗?3 缁勶細`offset=40 limit=20`

鎺ㄨ崘椤哄簭锛?

1. 鍏堣窇鍙洖妫€绱㈤樁娈点€?
2. 鍐嶈窇绮剧‘鐜囩敓鎴愰樁娈点€?
3. 鍐嶈窇骞昏鐜囩敓鎴愰樁娈点€?
4. 鏈€鍚庡湪纭鍓嶉潰缁撴灉閮藉凡钀界洏鍚庯紝鍐嶅垎缁勮窇 judge銆?

杩欐牱鍗充娇涓€?token 涓嶅锛屽墠闈㈢殑鍘熷缁撴灉涔熷凡缁忎繚浣忋€?


## 7. 鍙洖鐜囪剼鏈?

### 7.1 鍙仛妫€绱紝涓嶅仛 judge

绗?1 缁勶細

```bash
python3 experiments/RAG/eval_recall.py --graph-name RAG --phase retrieve --offset 0 --limit 20 --batch-size 20 --append
```

绗?2 缁勶細

```bash
python3 experiments/RAG/eval_recall.py --graph-name RAG --phase retrieve --offset 20 --limit 20 --batch-size 20 --append
```

绗?3 缁勶細

```bash
python3 experiments/RAG/eval_recall.py --graph-name RAG --phase retrieve --offset 40 --limit 20 --batch-size 20 --append
```

杩欎竴姝ョ粨鏉熷悗锛宍recall_eval.json` 閲屼細鍏堜繚瀛樻绱㈢粨鏋滐紝浣嗚繕娌℃湁鏈€缁堝彫鍥炵巼缁熻銆?


### 7.2 鏈€鍚庡啀鍋?judge

绗?1 缁勶細

```bash
python3 experiments/RAG/eval_recall.py --graph-name RAG --phase judge --offset 0 --limit 20 --batch-size 50 --append
```

绗?2 缁勶細

```bash
python3 experiments/RAG/eval_recall.py --graph-name RAG --phase judge --offset 20 --limit 20 --batch-size 20 --append
```

绗?3 缁勶細

```bash
python3 experiments/RAG/eval_recall.py --graph-name RAG --phase judge --offset 40 --limit 20 --batch-size 50 --append
```

瀹屾垚鍚庢煡鐪嬶細

- `experiments/RAG/eval_outputs/recall_eval.json`
- `experiments/RAG/eval_outputs/recall_eval.md`


## 8. 绮剧‘鐜囪剼鏈?

### 8.1 鍏堢敓鎴愭湁 RAG 鐨勫洖绛?

绗?1 缁勶細

```bash
python3 experiments/RAG/eval_precision.py --graph-name RAG --phase generate --top-k 1 3 --offset 0 --limit 20 --batch-size 20 --append
```

绗?2 缁勶細

```bash
python3 experiments/RAG/eval_precision.py --graph-name RAG --phase generate --top-k 1 3 --offset 20 --limit 20 --batch-size 20 --append
```

绗?3 缁勶細

```bash
python3 experiments/RAG/eval_precision.py --graph-name RAG --phase generate --top-k 1 3 --offset 40 --limit 20 --batch-size 20 --append
```

瀹屾垚鍚庝細寰楀埌锛?

- `precision_top1.json`
- `precision_top1.md`
- `precision_top3.json`
- `precision_top3.md`

鍏朵腑 `.md` 鏂囦欢閲屽凡缁忔湁浣犺鐨勫洖绛旇〃锛?

- `缂栧彿`
- `娴嬭瘯鐢ㄤ緥鍐呭`
- `鍥炵瓟鍐呭`


### 8.2 鏈€鍚庡啀鍋?judge

绗?1 缁勶細

```bash
python3 experiments/RAG/eval_precision.py \
  --graph-name YOUR_GRAPH_NAME \
  --phase judge \
  --top-k 1 3 \
  --offset 0 \
  --limit 20 \
  --batch-size 20 \
  --append
```

绗?2 缁勶細

```bash
python3 experiments/RAG/eval_precision.py \
  --graph-name YOUR_GRAPH_NAME \
  --phase judge \
  --top-k 1 3 \
  --offset 20 \
  --limit 20 \
  --batch-size 20 \
  --append
```

绗?3 缁勶細

```bash
python3 experiments/RAG/eval_precision.py \
  --graph-name YOUR_GRAPH_NAME \
  --phase judge \
  --top-k 1 3 \
  --offset 40 \
  --limit 20 \
  --batch-size 20 \
  --append
```

瀹屾垚鍚庨澶栦細寰楀埌锛?

- `precision_summary.md`


## 9. 骞昏鐜囪剼鏈?

### 9.1 鍏堢敓鎴愭棤 RAG 鍥炵瓟锛屽苟澶嶇敤鏈?RAG 缁撴灉

榛樿浼氫紭鍏堝鐢細

- `experiments/RAG/eval_outputs/precision_top3.json`

鎵€浠ュ缓璁厛瀹屾垚绮剧‘鐜囪剼鏈殑鐢熸垚闃舵銆?

绗?1 缁勶細

```bash
python3 experiments/RAG/eval_hallucination.py --phase generate --offset 0 --limit 20 --batch-size 20 --append
```

绗?2 缁勶細

```bash
python3 experiments/RAG/eval_hallucination.py --phase generate --offset 20 --limit 20 --batch-size 20 --append
```

绗?3 缁勶細

```bash
python3 experiments/RAG/eval_hallucination.py --phase generate --offset 40 --limit 20 --batch-size 20 --append
```

濡傛灉浣犳兂鏄惧紡鎸囧畾澶嶇敤鐨勬湁 RAG 缁撴灉鏂囦欢锛?

```bash
python3 experiments/RAG/eval_hallucination.py \
  --phase generate \
  --rag-results experiments/RAG/eval_outputs/precision_top3.json \
  --offset 0 \
  --limit 20 \
  --batch-size 20 \
  --append
```


### 9.2 鏈€鍚庡啀鍋?judge

绗?1 缁勶細

```bash
python3 experiments/RAG/eval_hallucination.py \
  --phase judge \
  --offset 0 \
  --limit 20 \
  --batch-size 20 \
  --append
```

绗?2 缁勶細

```bash
python3 experiments/RAG/eval_hallucination.py \
  --phase judge \
  --offset 20 \
  --limit 20 \
  --batch-size 20 \
  --append
```

绗?3 缁勶細

```bash
python3 experiments/RAG/eval_hallucination.py \
  --phase judge \
  --offset 40 \
  --limit 20 \
  --batch-size 20 \
  --append
```

瀹屾垚鍚庢煡鐪嬶細

- `hallucination_eval.json`
- `hallucination_eval.md`


## 10. 甯歌闂

### 10.1 涓轰粈涔堣鍒嗛樁娈?

鍥犱负 judge 涔熻娑堣€?token銆傚厛瀹屾垚鐢熸垚骞惰惤鐩橈紝鑳介伩鍏嶄腑閫?token 鐢ㄥ敖鏃朵涪澶卞墠闈㈢殑缁撴灉銆?


### 10.2 涓轰粈涔堣 `--append`

鍥犱负浣犵幇鍦ㄦ槸鎸?20 鏉′竴缁勬帹杩涖€俙--append` 浼氭妸姣忎竴缁勭粨鏋滃悎骞惰繘鎬绘枃浠讹紝鑰屼笉鏄鐩栧墠涓€缁勩€?


### 10.3 濡傛灉鍚屼竴缁勮窇閿欎簡鎬庝箞鍔?

鐩存帴瀵瑰悓鏍风殑 `offset + limit` 鍐嶈窇涓€娆★紝骞剁户缁甫 `--append` 鍗冲彲銆?

鑴氭湰浼氭寜 `case_id` 瑕嗙洊鏇存柊锛屼笉浼氶噸澶嶅爢绉€?


### 10.4 骞昏鐜囪剼鏈负浠€涔堥粯璁ゅ鐢?`precision_top3.json`

鍥犱负瀹冮渶瑕佲€滄湁 RAG 鐨勫洖绛斺€濄€傝繖浠界粨鏋滄濂芥潵鑷簿纭巼鑴氭湰鐨勭敓鎴愰樁娈碉紝閫傚悎浣滀负澶嶇敤鏉ユ簮銆?


## 11. 鏈€绠€鎺ㄨ崘鍛戒护

濡傛灉浣犲彧鎯崇収鎶勶細

### 绗竴杞細鍏堟妸鐢熸垚鍏ㄩ儴璺戝畬

```bash
python3 experiments/RAG/eval_recall.py --graph-name YOUR_GRAPH_NAME --phase retrieve --offset 0 --limit 20 --batch-size 20 --append
python3 experiments/RAG/eval_recall.py --graph-name YOUR_GRAPH_NAME --phase retrieve --offset 20 --limit 20 --batch-size 20 --append
python3 experiments/RAG/eval_recall.py --graph-name YOUR_GRAPH_NAME --phase retrieve --offset 40 --limit 20 --batch-size 20 --append

python3 experiments/RAG/eval_precision.py --graph-name YOUR_GRAPH_NAME --phase generate --top-k 1 3 --offset 0 --limit 20 --batch-size 20 --append
python3 experiments/RAG/eval_precision.py --graph-name YOUR_GRAPH_NAME --phase generate --top-k 1 3 --offset 20 --limit 20 --batch-size 20 --append
python3 experiments/RAG/eval_precision.py --graph-name YOUR_GRAPH_NAME --phase generate --top-k 1 3 --offset 40 --limit 20 --batch-size 20 --append

python3 experiments/RAG/eval_hallucination.py --phase generate --offset 0 --limit 20 --batch-size 20 --append
python3 experiments/RAG/eval_hallucination.py --phase generate --offset 20 --limit 20 --batch-size 20 --append
python3 experiments/RAG/eval_hallucination.py --phase generate --offset 40 --limit 20 --batch-size 20 --append
```

### 绗簩杞細鏈€鍚庣粺涓€璺?judge

```bash
python3 experiments/RAG/eval_recall.py --graph-name YOUR_GRAPH_NAME --phase judge --offset 0 --limit 20 --batch-size 20 --append
python3 experiments/RAG/eval_recall.py --graph-name YOUR_GRAPH_NAME --phase judge --offset 20 --limit 20 --batch-size 20 --append
python3 experiments/RAG/eval_recall.py --graph-name YOUR_GRAPH_NAME --phase judge --offset 40 --limit 20 --batch-size 20 --append

python3 experiments/RAG/eval_precision.py --graph-name YOUR_GRAPH_NAME --phase judge --top-k 1 3 --offset 0 --limit 20 --batch-size 20 --append
python3 experiments/RAG/eval_precision.py --graph-name YOUR_GRAPH_NAME --phase judge --top-k 1 3 --offset 20 --limit 20 --batch-size 20 --append
python3 experiments/RAG/eval_precision.py --graph-name YOUR_GRAPH_NAME --phase judge --top-k 1 3 --offset 40 --limit 20 --batch-size 20 --append

python3 experiments/RAG/eval_hallucination.py --phase judge --offset 0 --limit 20 --batch-size 20 --append
python3 experiments/RAG/eval_hallucination.py --phase judge --offset 20 --limit 20 --batch-size 20 --append
python3 experiments/RAG/eval_hallucination.py --phase judge --offset 40 --limit 20 --batch-size 20 --append
```



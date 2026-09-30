/* example_scenes.js — pixel.js の使い方の見本（2 場面）
 * 規約: グローバル SCENES = [{ name, dur, draw(t), cap(t) }]。draw は毎回 clear() 済みの画面に描く。 */

// 場面ごとの定数は場面の外で一度だけ作る（毎コマ作り直さない）
const K = V3.norm([0.5, 0.35, 1]);
const V = [1.5, -0.3, 0.35];

// 画面に出す行列の成分は、表示用の文字列を定数にして、同じ文字列を検算にも使う
const RZ = [['COSθ', '−SINθ', '0'], ['SINθ', 'COSθ', '0'], ['0', '0', '1']];
for (const th of [0.7, 2.1]) {
  // 正しい値: z 軸まわりに単位ベクトル e_c を回したときの成分 r（定義から計算）
  for (let c = 0; c < 3; c++) {
    const e = [0, 0, 0]; e[c] = 1;
    const rotated = [e[0] * Math.cos(th) - e[1] * Math.sin(th), e[0] * Math.sin(th) + e[1] * Math.cos(th), e[2]];
    for (let r = 0; r < 3; r++) checkExpr(RZ[r][c], { θ: th }, rotated[r], 'RZ(' + r + ',' + c + ')');
  }
}

const SCENES = [
  {
    name: 'データの流れ',
    dur: 6,
    draw(t) {
      title('0', 'DATA FLOWS LEFT TO RIGHT');
      const boxes = [['INPUT', 20], ['MODEL', 130], ['OUTPUT', 240]];
      const on = Math.floor(t / 2) % 3;                         // 2 秒ごとに光る箱が進む
      boxes.forEach(([lab, x], i) => {
        box(x, 60, 60, 30, i === on ? '#2a2540' : C.panel, i === on ? C.gold : C.line);
        text(lab, x + 30, 72, i === on ? C.gold : C.ink, 'center');
      });
      const p1 = [[80, 75], [130, 75]], p2 = [[190, 75], [240, 75]];
      wire(p1, C.blue); wire(p2, C.pink);
      packets(p1, C.blue, t); packets(p2, C.pink, t);
      bar(20, 120, 280, 8, t / 6, C.teal);                     // 進捗バー
      text('PROGRESS ' + Math.round(clamp(t / 6) * 100) + '%', 160, 134, C.ink2, 'center');
    },
    cap: t => t < 3 ? '左の入力がモデルを通って、右の出力になる。' : '光っている箱が、いま処理している段階。',
  },
  {
    name: '行列と3D',
    dur: 7,
    draw(t) {
      title('1', 'MATRIX AND 3D');
      // 3D: 軸 K のまわりを V が回る
      CAM.ox = 80; CAM.oy = 110; CAM.scale = 38; CAM.yaw = -0.5 + Math.sin(t * .3) * .2;
      axes3();
      line3(V3.mul(K, -1), V3.mul(K, 2), C.gold);
      const th = 0.8 + t * 0.7, kv = V3.cross(K, V);
      const rot = V3.add(V3.mul(V, Math.cos(th)), V3.mul(kv, Math.sin(th)), V3.mul(K, V3.dot(K, V) * (1 - Math.cos(th))));
      arrow3([0, 0, 0], V, C.blue, 'V');
      arrow3([0, 0, 0], rot, C.pink, "V'");
      text('θ = ' + Math.round((th * 180 / Math.PI) % 360) + '°', 12, 20, C.ink);
      // 行列: 色つきの成分は [[文字列, 色], ...]
      const col = s => /SIN/.test(s) ? C.red : s === '1' ? C.teal : C.ink;
      const cells = RZ.map(row => row.map(s => [s, col(s)]));   // 検算したのと同じ文字列を表示する
      text('R =', 196, 64, C.ink, 'right');
      matrix(202, 52, cells, 30);                              // 列幅 30 = 最長 5 文字 × 4 + 10
      segs(170, 110, [['RED', C.red], [' = SIN PART', C.ink2]]);
    },
    cap: t => 'z 軸まわりの回転。左は 3D の図、右は回転行列。',
  },
];

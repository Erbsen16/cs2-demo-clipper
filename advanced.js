// Local layout reference. All scene coordinates use the same 720-unit height
// as the ASS baseline. The viewport width follows the selected aspect ratio.
const advancedElement = id => document.getElementById(id);
const baseLayout = {
  ratio: '16:9', size: '1280x720', fps: 24, crf: 18, camera: 'eyes',
  fov: 60, radar: 1, zoom: 0.7, position: 'radar', x: 1, y: 41, fontSize: 32,
};
let availableSizes;
let advancedFrame;
const matchFrame = new Image();
matchFrame.onload = refreshReference;
matchFrame.src = './preview-frame.jpg';

function readLayout() {
  const values = {};
  for (const [key, fallback] of Object.entries(baseLayout)) {
    const input = advancedElement(key);
    values[key] = typeof fallback === 'number' ? Number(input.value) : input.value;
  }
  return values;
}

function advancedPayload() {
  return advancedElement('advancedOn').checked ? readLayout() : null;
}

function advancedControls(busy) {
  const toggle = advancedElement('advancedOn');
  const panel = advancedElement('advancedPanel');
  toggle.disabled = busy || !availableSizes;
  toggle.setAttribute('aria-expanded', String(toggle.checked));
  panel.hidden = !toggle.checked;
  panel.disabled = busy || !toggle.checked;
}

function drawReference(canvas, layout) {
  const [width, height] = layout.size.split('x').map(Number);
  const w = width * 720 / height;
  // Limit bitmap memory on repeated slider moves. CSS fits the full field of view.
  canvas.width = Math.min(width, 1280);
  canvas.height = Math.round(canvas.width * height / width);
  const g = canvas.getContext('2d');
  g.scale(canvas.width / w, canvas.height / 720);
  const rect = (x,y,b,h,color) => { g.fillStyle=color; g.fillRect(x,y,b,h); };
  function polygon(points, color) {
    g.beginPath();
    points.forEach(([x,y],i) => i ? g.lineTo(x,y) : g.moveTo(x,y));
    g.closePath(); g.fillStyle=color; g.fill();
  }
  function line(a,b,color,size=1) {
    g.beginPath(); g.moveTo(...a); g.lineTo(...b);
    g.strokeStyle=color; g.lineWidth=size; g.stroke();
  }
  function dot(x,y,r,color) {
    g.beginPath(); g.arc(x,y,r,0,Math.PI*2); g.fillStyle=color; g.fill();
  }

  const chase = layout.camera === 'chase';
  const sky = g.createLinearGradient(0,0,0,405);
  sky.addColorStop(0,'#648ba2'); sky.addColorStop(1,'#d7d1b6');
  rect(0,0,w,405,sky);
  const ground=g.createLinearGradient(0,325,0,720);
  ground.addColorStop(0,'#aa9c86');ground.addColorStop(1,'#827467');
  rect(0,325,w,395,ground);
  // A simple courtyard in perspective to make horizontal crop and camera height visible.
  function project(x,y,z) {
    const depth=z+(chase ? 3.3 : 0);
    return [w/2+560*x/depth, (chase ? 300 : 324)+560*((chase ? 2.55 : 1.62)-y)/depth];
  }
  function wall(points,color) { polygon(points.map(p=>project(...p)),color); }
  for(let z=2;z<35;z+=1.8) line(project(-12,0,z),project(12,0,z),'#897d6d');
  for(let x=-10;x<=10;x+=1.4) line(project(x,0,1),project(x,0,34),'#958675');
  function building(x,z,b,d,h,front,side) {
    wall([[x,0,z],[x+b,0,z],[x+b,h,z],[x,h,z]],front);
    const edge=x<0 ? x+b : x;
    wall([[edge,0,z],[edge,0,z+d],[edge,h,z+d],[edge,h,z]],side);
    wall([[x,h,z],[x+b,h,z],[x+b,h+.2,z],[x,h+.2,z]],'#76584a');
    for(let i=.55;i<b-.65;i+=1.5) {
      wall([[x+i,2.05,z],[x+i+.72,2.05,z],[x+i+.72,3,z],[x+i,3,z]],'#435650');
    }
  }
  building(-5,22,12,3,4.9,'#d7bb8f','#a99172');
  building(-8,8,5,8,5.5,'#ceb18f','#b89a79');
  building(3.2,6,6,13,4.5,'#dfc69e','#b7a38a');
  building(-7,3,3.9,6,4.1,'#ae8675','#bb9985');
  building(.7,12,1.7,1.2,1.7,'#957857','#705f4a');
  const cx=w/2;
  if (chase) {
    // Back-facing figure is a camera reference, not a character asset.
    g.save();g.translate(cx,460);
    polygon([[-37,56],[0,51],[-7,179],[-43,180]],'#2f383d');
    polygon([[1,51],[38,55],[48,179],[10,180]],'#384349');
    polygon([[-51,-45],[-20,-64],[26,-63],[53,-36],[37,64],[-38,64]],'#49594d');
    rect(-33,-40,66,74,'#343f39');rect(-23,-18,46,34,'#606751');
    dot(0,-78,29,'#414b44');g.restore();
  } else {
    g.save();g.translate(w*.77,720);
    const scale=60/layout.fov; g.scale(scale,scale);
    polygon([[-42,-68],[17,-95],[141,0],[22,0]],'#6a5547');
    polygon([[-76,-133],[-21,-138],[7,-70],[-23,-51],[-55,-70]],'#4a504e');
    polygon([[-103,-174],[-88,-184],[-17,-155],[-25,-132],[-95,-153]],'#313a40');
    polygon([[-88,-184],[-68,-183],[0,-156],[-17,-155]],'#85908f');g.restore();
    line([cx-5,360],[cx+5,360],'#c6e5c1',1.5);
    line([cx,355],[cx,365],'#c6e5c1',1.5);
  }

  if (!chase && matchFrame.complete && matchFrame.naturalWidth) {
    const width = Math.min(970, 970 * w / 1280);
    const height = width * 720 / w;
    g.drawImage(matchFrame, 275 + (970-width)/2, 720-height, width, height, 0, 0, w, 720);
  }
  const side=250*layout.radar;
  g.save();g.translate(5,5);
  rect(0,0,side,side,'#192129');
  g.beginPath();g.rect(0,0,side,side);g.clip();
  g.translate(side/2,side/2);g.scale(side/250*layout.zoom/.7,side/250*layout.zoom/.7);
  const rooms=[[-122,-91,68,32],[-91,-68,29,83],[-73,-18,75,28],[-15,-58,32,75],
               [1,-59,79,25],[61,-82,51,44],[54,-39,24,103],[1,51,77,25],[-19,2,28,81],[-80,67,76,20]];
  rooms.forEach(r=>rect(...r,'#788283'));
  g.fillStyle='#edc075';g.font='bold 19px Arial';g.fillText('A',79,-54);g.fillText('B',-113,-70);
  dot(-40,-8,4,'#62b4df');dot(66,34,4,'#deb863');
  polygon([[0,-8],[-5,5],[5,5]],'#fff');g.restore();
  g.fillStyle='#ead9a9';g.font='18px sans-serif';g.textAlign='center';g.fillText('中路',5+side/2,side+25);

  if(advancedElement('counter').value !== '不显示') {
    const custom=layout.position==='custom';
    const x=custom ? w*layout.x/100 : 12;
    const y=custom ? 720*layout.y/100 : 44+side;
    g.textAlign=custom && layout.x>50 ? 'right':'left';
    g.textBaseline='top';g.fillStyle='white';g.font='bold '+layout.fontSize+'px Arial';
    const value=advancedElement('counter').value==='击杀-死亡' ? 'i20' : '1';
    g.fillText((advancedElement('showLabel').checked ? 'KILLS  ' : '')+value,x,y);
  }
}

function refreshReference() {
  if (!availableSizes || !advancedElement('advancedOn').checked) return;
  const val=readLayout();
  for (const key of ['fov','radar','zoom','x','y','fontSize']) {
    advancedElement(key+'Value').textContent=val[key]+(['x','y'].includes(key) ? '%' : '');
  }
  advancedElement('fov').disabled=val.camera==='chase';
  const hidden=advancedElement('counter').value==='不显示';
  advancedElement('position').disabled=hidden;
  for(const id of ['x','y']) advancedElement(id).disabled=hidden || val.position!=='custom';
  advancedElement('currentSize').textContent=val.size.replace('x',' × ')+' · '+val.fps+' fps · CRF '+val.crf;
  cancelAnimationFrame(advancedFrame);
  advancedFrame=requestAnimationFrame(()=>{
    drawReference(advancedElement('baseline'),baseLayout);
    drawReference(advancedElement('changes'),val);
  });
}

function initAdvanced(sizes) {
  availableSizes=sizes;
  const ratio=advancedElement('ratio'), size=advancedElement('size');
  ratio.replaceChildren(...Object.keys(sizes).map(r=>new Option(r,r)));
  function updateSizes() {
    const tier=Math.max(size.selectedIndex,0);
    size.replaceChildren(...sizes[ratio.value].map(([w,h])=>new Option(w+' × '+h,w+'x'+h)));
    size.selectedIndex=tier;
    refreshReference();
  }
  updateSizes();
  ratio.onchange=updateSizes;
  const toggle=advancedElement('advancedOn');
  toggle.checked=false;
  toggle.onchange=()=>{advancedControls(busy);refreshReference();};
  advancedElement('advancedPanel').addEventListener('input', refreshReference);
  for(const id of ['counter','showLabel']) advancedElement(id).addEventListener('change',refreshReference);
  const canvas=advancedElement('changes');
  function place(event) {
    if(busy || advancedElement('counter').value==='不显示') return;
    const rect=canvas.getBoundingClientRect();
    advancedElement('position').value='custom';
    advancedElement('x').value=Math.max(0,Math.min(100,100*(event.clientX-rect.left)/rect.width));
    advancedElement('y').value=Math.max(0,Math.min(94,100*(event.clientY-rect.top)/rect.height));
    refreshReference();
  }
  canvas.onpointerdown=event=>{canvas.setPointerCapture(event.pointerId);place(event);};
  canvas.onpointermove=event=>{if(canvas.hasPointerCapture(event.pointerId)) place(event);};
  advancedControls(busy);
}

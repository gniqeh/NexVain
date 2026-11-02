const data=[["示例 A",23],["示例 B",41],["示例 C",30],["示例 D",55]];
const chart=document.getElementById("chart");
const grid=document.createElement("div");grid.className="barline";
const max=Math.max(...data.map(x=>x[1]));
for(const [label,value] of data){
 const bar=document.createElement("div");bar.className="bar";
 bar.style.height=(value/max*100)+"%";bar.title=label+"："+value;
 const caption=document.createElement("span");caption.textContent=label;bar.append(caption);grid.append(bar);
}
chart.append(grid);
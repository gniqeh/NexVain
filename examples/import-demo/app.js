"use strict";
// 自包含的交互演示。没有 API 请求，也没有第三方 CDN。
const scenarios=[
  [{name:"2022",value:46},{name:"2023",value:62},{name:"2024",value:55},{name:"2025",value:79}],
  [{name:"2022",value:32},{name:"2023",value:48},{name:"2024",value:73},{name:"2025",value:66}]
];
let current=0;
function render(){
 const chart=document.getElementById("chart");
 chart.replaceChildren();
 const values=scenarios[current];
 const max=Math.max(...values.map(x=>x.value));
 for(const item of values){
  const bar=document.createElement("div");
  bar.className="bar";
  bar.style.height=(item.value/max*100)+"%";
  bar.title=item.name+"： "+item.value+"（演示）";
  const label=document.createElement("span");
  label.textContent=item.name;
  bar.append(label);
  chart.append(bar);
 }
}
document.getElementById("toggle").addEventListener("click",()=>{current=(current+1)%scenarios.length;render()});
render();
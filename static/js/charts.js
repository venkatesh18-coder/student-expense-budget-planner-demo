// Renders dashboard charts from JSON embedded by Flask (real database data).
const d = JSON.parse(document.getElementById("chart-data").textContent);
const colors = ["#12332b","#e9a23b","#1f8a5b","#d64550","#2f6db5","#6b46c1","#1b8a8a","#b7791f","#8a9a94","#c05621","#4a5568","#9f7aea"];
const empty = (id, hasData) => { if (!hasData) document.getElementById(id).parentElement.innerHTML = '<p class="text-muted text-center pt-5">No data yet. Add some transactions.</p>'; return hasData; };
if (empty("catChart", d.categories.values.length))
  new Chart("catChart", {type:"doughnut", data:{labels:d.categories.labels, datasets:[{data:d.categories.values, backgroundColor:colors}]}, options:{maintainAspectRatio:false, plugins:{legend:{position:"bottom"}}}});
new Chart("ieChart", {type:"bar", data:{labels:d.months, datasets:[{label:"Income", data:d.income, backgroundColor:"#1f8a5b", borderRadius:6},{label:"Expense", data:d.expense, backgroundColor:"#d64550", borderRadius:6}]}, options:{maintainAspectRatio:false, scales:{y:{beginAtZero:true}}}});
new Chart("trendChart", {type:"line", data:{labels:d.months, datasets:[{label:"Spending", data:d.expense, borderColor:"#e9a23b", backgroundColor:"rgba(233,162,59,.15)", fill:true, tension:.35}]}, options:{maintainAspectRatio:false, scales:{y:{beginAtZero:true}}}});

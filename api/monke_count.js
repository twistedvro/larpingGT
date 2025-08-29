mport { ChartJSNodeCanvas } from 'chartjs-node-canvas';

let playerHistory = []; // last 24 entries
let peakCount = 0;

const WIDTH = 600;
const HEIGHT = 400;
const chartJSNodeCanvas = new ChartJSNodeCanvas({ width: WIDTH, height: HEIGHT });

export default async function handler(req, res) {
  if (req.method === 'POST') {
    const { player_count } = req.body;
    const count = parseInt(player_count) || 0;

    peakCount = Math.max(peakCount, count);

    playerHistory.push({ time: new Date(), count });
    if (playerHistory.length > 24) playerHistory.shift();

    return res.status(200).json({ success: true });
  } 
  else if (req.method === 'GET') {
    // Create chart with current count + peak as overlay text
    const currentCount = playerHistory.length ? playerHistory[playerHistory.length - 1].count : 0;

    const configuration = {
      type: 'line',
      data: {
        labels: playerHistory.map(e => e.time.toLocaleTimeString()),
        datasets: [{
          label: 'Monke Count',
          data: playerHistory.map(e => e.count),
          borderColor: 'orange',
          backgroundColor: 'rgba(255,165,0,0.2)',
          fill: true,
          tension: 0.3
        }],
      },
      options: {
        plugins: {
          title: {
            display: true,
            text: `Current: ${currentCount} | Peak: ${peakCount}`,
            font: { size: 18 }
          }
        },
        scales: {
          y: { beginAtZero: true },
        },
      },
    };

    const image = await chartJSNodeCanvas.renderToBuffer(configuration, 'image/png');

    res.setHeader('Content-Type', 'image/png');
    res.send(image);
  } 
  else {
    res.setHeader('Allow', ['POST', 'GET']);
    res.status(405).end(`Method ${req.method} Not Allowed`);
  }
}

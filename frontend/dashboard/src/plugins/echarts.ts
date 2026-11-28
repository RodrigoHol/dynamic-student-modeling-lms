import { use } from "echarts/core";
import { CanvasRenderer } from "echarts/renderers";
import { BarChart, SankeyChart } from "echarts/charts";
import {
  GridComponent,
  LegendComponent,
  TooltipComponent,
} from "echarts/components";

use([CanvasRenderer, SankeyChart, BarChart, TooltipComponent, GridComponent, LegendComponent]);

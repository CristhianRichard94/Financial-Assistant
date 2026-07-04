import { Router, type IRouter } from "express";
import healthRouter from "./health";
import finsightRouter from "./finsight";

const router: IRouter = Router();

router.use(healthRouter);
router.use(finsightRouter);

export default router;

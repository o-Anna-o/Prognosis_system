import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useReducer,
  type ReactNode,
} from "react";
import type { ApartmentInput, PredictionResult } from "../shared/api/types";
import type {
  ApartmentParameterPatch,
  ApartmentState,
  ApartmentsState,
} from "../features/apartments/types";

type ApartmentsAction =
  | { type: "apartment/added"; id: string; parameters: ApartmentInput }
  | { type: "apartment/removed"; id: string }
  | { type: "apartment/parametersChanged"; id: string; patch: ApartmentParameterPatch }
  | { type: "apartment/predictionSet"; id: string; prediction: PredictionResult }
  | { type: "apartments/predictionsSet"; predictions: { id: string; prediction: PredictionResult }[] }
  | { type: "apartment/predictionStarted"; id: string }
  | { type: "apartment/predictionFailed"; id: string; error: string }
  | { type: "apartment/errorCleared"; id: string }
  | { type: "apartment/predictionCancelled"; id: string }
  | { type: "apartments/reset" }
  | { type: "apartment/collapseToggled"; id: string }
  | { type: "apartments/collapsedSet"; collapsed: boolean }
  | { type: "apartment/activated"; id: string };

interface ApartmentsStateContextValue extends ApartmentsState {
  getApartment: (id: string) => ApartmentState | undefined;
}

interface ApartmentsActionsContextValue {
  addApartment: (parameters?: ApartmentInput) => string;
  removeApartment: (id: string) => void;
  updateApartmentParameters: (id: string, patch: ApartmentParameterPatch) => void;
  setApartmentPrediction: (id: string, prediction: PredictionResult) => void;
  setApartmentPredictions: (predictions: { id: string; prediction: PredictionResult }[]) => void;
  startApartmentPrediction: (id: string) => void;
  cancelApartmentPrediction: (id: string) => void;
  setApartmentError: (id: string, error: string | null) => void;
  resetApartments: () => void;
  toggleApartmentCollapsed: (id: string) => void;
  setApartmentsCollapsed: (collapsed: boolean) => void;
  setActiveApartment: (id: string) => void;
}

const ApartmentsStateContext = createContext<ApartmentsStateContextValue | null>(null);
const ApartmentsActionsContext = createContext<ApartmentsActionsContextValue | null>(null);

const initialState: ApartmentsState = {
  apartments: [],
  activeApartmentId: null,
  nextOrder: 1,
};

function createEmptyParameters(): ApartmentInput {
  return {
    region: "",
    district: "",
    street: "",
    wall_material: "",
    year_build: "",
    floor: "",
    area: "",
    n_years: "",
  };
}

function apartmentsReducer(state: ApartmentsState, action: ApartmentsAction): ApartmentsState {
  switch (action.type) {
    case "apartment/added": {
      const apartment: ApartmentState = {
        id: action.id,
        order: state.nextOrder,
        formRevision: 0,
        parameters: action.parameters,
        prediction: null,
        isPredictionStale: false,
        isCollapsed: false,
        isCalculating: false,
        error: null,
      };

      return {
        apartments: [...state.apartments, apartment],
        activeApartmentId: apartment.id,
        nextOrder: state.nextOrder + 1,
      };
    }
    case "apartment/removed": {
      const apartments = state.apartments.filter((apartment) => apartment.id !== action.id);
      const activeApartmentId =
        state.activeApartmentId === action.id
          ? (apartments[0]?.id ?? null)
          : state.activeApartmentId;

      return apartments.length === state.apartments.length
        ? state
        : { ...state, apartments, activeApartmentId };
    }
    case "apartment/parametersChanged": {
      let changed = false;
      const apartments = state.apartments.map((apartment) => {
        if (apartment.id !== action.id) return apartment;

        const hasChanges = Object.entries(action.patch).some(
          ([key, value]) => apartment.parameters[key as keyof ApartmentInput] !== value,
        );
        if (!hasChanges) return apartment;

        changed = true;
        return {
          ...apartment,
          parameters: { ...apartment.parameters, ...action.patch },
          isPredictionStale: apartment.prediction !== null || apartment.isPredictionStale,
        };
      });

      return changed ? { ...state, apartments } : state;
    }
    case "apartment/predictionSet":
      return {
        ...state,
        apartments: state.apartments.map((apartment) =>
          apartment.id === action.id
            ? { ...apartment, prediction: action.prediction, isPredictionStale: false, isCalculating: false, error: null }
            : apartment,
        ),
      };
    case "apartments/predictionsSet": {
      const predictions = new Map(action.predictions.map(({ id, prediction }) => [id, prediction]));
      return {
        ...state,
        apartments: state.apartments.map((apartment) => {
          const prediction = predictions.get(apartment.id);
          return prediction
            ? { ...apartment, prediction, isPredictionStale: false, isCalculating: false, error: null }
            : apartment;
        }),
      };
    }
    case "apartment/predictionStarted":
      return { ...state, apartments: state.apartments.map((apartment) => apartment.id === action.id ? { ...apartment, isCalculating: true, error: null } : apartment) };
    case "apartment/predictionFailed":
      return { ...state, apartments: state.apartments.map((apartment) => apartment.id === action.id ? { ...apartment, isCalculating: false, error: action.error } : apartment) };
    case "apartment/errorCleared":
      return { ...state, apartments: state.apartments.map((apartment) => apartment.id === action.id ? { ...apartment, error: null } : apartment) };
    case "apartment/predictionCancelled":
      return { ...state, apartments: state.apartments.map((apartment) => apartment.id === action.id ? { ...apartment, isCalculating: false, error: null } : apartment) };
    case "apartments/reset": {
      const first = state.apartments[0];
      if (!first) return initialState;
      return {
        apartments: [{
          ...first,
          order: 1,
          formRevision: first.formRevision + 1,
          parameters: createEmptyParameters(),
          prediction: null,
          isPredictionStale: false,
          isCalculating: false,
          error: null,
        }],
        activeApartmentId: first.id,
        nextOrder: 2,
      };
    }
    case "apartment/collapseToggled":
      return {
        ...state,
        apartments: state.apartments.map((apartment) =>
          apartment.id === action.id
            ? { ...apartment, isCollapsed: !apartment.isCollapsed }
            : apartment,
        ),
      };
    case "apartments/collapsedSet":
      return { ...state, apartments: state.apartments.map((apartment) => ({ ...apartment, isCollapsed: action.collapsed })) };
    case "apartment/activated":
      return state.apartments.some((apartment) => apartment.id === action.id)
        ? { ...state, activeApartmentId: action.id }
        : state;
    default: {
      const exhaustiveCheck: never = action;
      return exhaustiveCheck;
    }
  }
}

interface ApartmentsProviderProps {
  children: ReactNode;
}

export function ApartmentsProvider({ children }: ApartmentsProviderProps) {
  const [state, dispatch] = useReducer(apartmentsReducer, initialState);

  const addApartment = useCallback(
    (parameters: ApartmentInput = createEmptyParameters()) => {
      const id = globalThis.crypto.randomUUID();
      dispatch({ type: "apartment/added", id, parameters });
      return id;
    },
    [],
  );
  const removeApartment = useCallback((id: string) => dispatch({ type: "apartment/removed", id }), []);
  const updateApartmentParameters = useCallback(
    (id: string, patch: ApartmentParameterPatch) =>
      dispatch({ type: "apartment/parametersChanged", id, patch }),
    [],
  );
  const setApartmentPrediction = useCallback(
    (id: string, prediction: PredictionResult) =>
      dispatch({ type: "apartment/predictionSet", id, prediction }),
    [],
  );
  const setApartmentPredictions = useCallback(
    (predictions: { id: string; prediction: PredictionResult }[]) =>
      dispatch({ type: "apartments/predictionsSet", predictions }),
    [],
  );
  const startApartmentPrediction = useCallback((id: string) => dispatch({ type: "apartment/predictionStarted", id }), []);
  const cancelApartmentPrediction = useCallback((id: string) => dispatch({ type: "apartment/predictionCancelled", id }), []);
  const setApartmentError = useCallback((id: string, error: string | null) => {
    dispatch(error ? { type: "apartment/predictionFailed", id, error } : { type: "apartment/errorCleared", id });
  }, []);
  const resetApartments = useCallback(() => dispatch({ type: "apartments/reset" }), []);
  const toggleApartmentCollapsed = useCallback(
    (id: string) => dispatch({ type: "apartment/collapseToggled", id }),
    [],
  );
  const setApartmentsCollapsed = useCallback((collapsed: boolean) => {
    dispatch({ type: "apartments/collapsedSet", collapsed });
  }, []);
  const setActiveApartment = useCallback((id: string) => dispatch({ type: "apartment/activated", id }), []);
  const getApartment = useCallback(
    (id: string) => state.apartments.find((apartment) => apartment.id === id),
    [state.apartments],
  );

  const stateValue = useMemo<ApartmentsStateContextValue>(
    () => ({ ...state, getApartment }),
    [state, getApartment],
  );
  const actionsValue = useMemo<ApartmentsActionsContextValue>(
    () => ({
      addApartment,
      removeApartment,
      updateApartmentParameters,
      setApartmentPrediction,
      setApartmentPredictions,
      startApartmentPrediction,
      cancelApartmentPrediction,
      setApartmentError,
      resetApartments,
      toggleApartmentCollapsed,
      setApartmentsCollapsed,
      setActiveApartment,
    }),
    [
      addApartment,
      removeApartment,
      updateApartmentParameters,
      setApartmentPrediction,
      setApartmentPredictions,
      startApartmentPrediction,
      cancelApartmentPrediction,
      setApartmentError,
      resetApartments,
      toggleApartmentCollapsed,
      setApartmentsCollapsed,
      setActiveApartment,
    ],
  );

  return (
    <ApartmentsStateContext.Provider value={stateValue}>
      <ApartmentsActionsContext.Provider value={actionsValue}>
        {children}
      </ApartmentsActionsContext.Provider>
    </ApartmentsStateContext.Provider>
  );
}

export function useApartmentsState(): ApartmentsStateContextValue {
  const context = useContext(ApartmentsStateContext);
  if (!context) throw new Error("useApartmentsState must be used within ApartmentsProvider");
  return context;
}

export function useApartmentsActions(): ApartmentsActionsContextValue {
  const context = useContext(ApartmentsActionsContext);
  if (!context) throw new Error("useApartmentsActions must be used within ApartmentsProvider");
  return context;
}
